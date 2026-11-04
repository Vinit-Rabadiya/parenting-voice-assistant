"""Aggregate privacy checks use synthetic records, never real conversations."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.api.dependencies import get_caregiver_data_service
from backend.core.privacy import CONSENT_VERSION
from backend.main import app
from backend.services.feedback_summary import (
    CONSENT_BATCH_SIZE, CONSENT_FIELDS, FeedbackSummaryService, MAX_DOCUMENTS_PER_GROUP,
    PROJECTED_FIELDS, summarize_feedback,
)
from scripts.set_feedback_admin import main, update_permission

NOW = datetime.now(timezone.utc) - timedelta(minutes=1)


def record(uid, *, name="a", rating=4, helpful=None, reasons=None, group="messages", when=NOW,
           comment="SHARED_FEEDBACK"):
    path = (f"users/{uid}/conversations/chat/messages/{name}" if group == "messages"
            else f"users/{uid}/interactions/{name}")
    return SimpleNamespace(reference=SimpleNamespace(path=path), to_dict=lambda: {
        "role": "assistant", "text": "PRIVATE_CHAT", "child_id": "PRIVATE_CHILD",
        "feedback": {"rating": rating, "helpful": helpful, "reasons": reasons or [],
                     "comment": comment, "recorded_at": when},
    })


def storage(messages=(), interactions=(), accepted=None):
    client = MagicMock()
    queries = {}
    for group, rows in (("messages", messages), ("interactions", interactions)):
        query = MagicMock()
        query.select.return_value = query
        query.limit.return_value = query
        query.stream.return_value = iter(rows)
        queries[group] = query
    client.collection_group.side_effect = lambda group: queries[group]

    def account(uid):
        value = (accepted or {}).get(uid, {"consent_version": CONSENT_VERSION,
                 "consent_at": NOW - timedelta(days=1), "caregiver_authority": True})
        reference = SimpleNamespace(path=f"users/{uid}")
        snapshot = SimpleNamespace(reference=reference, exists=bool(value), to_dict=lambda: value)
        reference.get = MagicMock(return_value=snapshot)
        reference.snapshot = snapshot
        return reference

    client.collection.return_value.document.side_effect = account
    client.get_all.side_effect = lambda references, **kwargs: (
        reference.snapshot for reference in reversed(references))
    return client, queries


def test_consent_reads_are_batched_projected_and_matched_by_path_instead_of_order():
    rows = [record(f"u{i}") for i in range(CONSENT_BATCH_SIZE + 3)]
    client, _ = storage(rows, accepted={"u0": {}, "u100": {}})
    report = FeedbackSummaryService(client).read()
    assert report.ratings[3].count == CONSENT_BATCH_SIZE + 1
    assert client.get_all.call_count == 2
    for call in client.get_all.call_args_list:
        assert len(call.args[0]) <= CONSENT_BATCH_SIZE
        assert call.kwargs == {"field_paths": CONSENT_FIELDS, "timeout": 5, "retry": None}
        for reference in call.args[0]:
            reference.get.assert_not_called()


def test_an_incomplete_consent_batch_never_publishes_partial_counts():
    client, _ = storage([record("one"), record("two")])
    client.get_all.side_effect = lambda references, **kwargs: [references[0].snapshot]
    with pytest.raises(RuntimeError, match="Incomplete aggregate consent"):
        FeedbackSummaryService(client).read()


def test_failed_consent_batch_cannot_publish_a_partial_report():
    client, _ = storage([record("one"), record("two")])
    def broken(references, **kwargs):
        yield references[0].snapshot
        raise RuntimeError("batch failed")
    client.get_all.side_effect = broken
    with pytest.raises(RuntimeError, match="batch failed"):
        FeedbackSummaryService(client).read()


def test_unexpected_consent_path_is_rejected():
    client, _ = storage([record("one")])
    client.get_all.side_effect = lambda references, **kwargs: [SimpleNamespace(
        reference=SimpleNamespace(path="users/other"))]
    with pytest.raises(RuntimeError, match="consent response"):
        FeedbackSummaryService(client).read()


@pytest.mark.parametrize("count", [0, 1, 4, 5, 9, 10])
def test_category_counts_include_the_first_response(count):
    result = summarize_feedback([{"rating": 4} for _ in range(count)])
    bucket = result.ratings[3]
    assert bucket.count == count
    assert result.ratings[0].count == 0
    assert "total" not in result.model_dump()


def test_feedback_on_different_answers_from_one_caregiver_counts_separately():
    client, _ = storage([record("one", name=str(i)) for i in range(20)])
    assert FeedbackSummaryService(client).read().ratings[3].count == 20


@pytest.mark.parametrize("version", ["2026-10-26.2", CONSENT_VERSION])
def test_health_notice_update_does_not_hide_already_shared_feedback(version):
    client, _ = storage([record("one")], accepted={"one": {
        "consent_version": version, "caregiver_authority": True,
        "consent_at": NOW + timedelta(seconds=1) if version == CONSENT_VERSION else NOW - timedelta(days=1),
        "feedback_consent_at": NOW - timedelta(days=1),
    }})
    report = FeedbackSummaryService(client).read()
    assert report.ratings[3].count == 1
    assert report.comment_count == 1


def test_synthetic_improvement_signal_contains_only_grouped_categories():
    result = summarize_feedback([{"rating": 2, "reasons": ["did_not_answer"]}])
    assert result.ratings[1].count == 1
    assert result.reasons[2].count == 1
    assert "synthetic" not in result.model_dump_json()
    assert all(bucket.count == 0 for bucket in result.legacy_helpfulness)


def test_each_answer_counts_and_legacy_scale_remains_separate():
    rows = [record(f"u{i}", name="old", rating=1) for i in range(5)]
    rows += [record(f"u{i}", name="new", rating=5, reasons=["unclear"],
                    when=NOW + timedelta(seconds=1)) for i in range(5)]
    legacy = [record(f"legacy{i}", rating=None, helpful=False, group="interactions") for i in range(5)]
    client, queries = storage(rows, legacy)
    result = FeedbackSummaryService(client).read()
    assert result.ratings[0].count == 5
    assert result.ratings[4].count == 5
    assert result.reasons[0].count == 5
    assert result.legacy_helpfulness[0].count == 0
    assert result.legacy_helpfulness[1].count == 5
    payload = result.model_dump_json()
    assert result.comments[0].comment == "SHARED_FEEDBACK"
    for forbidden in ("PRIVATE", "child_id", "recorded_at", "u0", "legacy0"):
        assert forbidden not in payload
    for query in queries.values():
        query.select.assert_called_once_with(PROJECTED_FIELDS)
        query.limit.assert_called_once_with(MAX_DOCUMENTS_PER_GROUP + 1)
    assert "feedback.comment" in PROJECTED_FIELDS
    assert not any("text" in field or "child" in field for field in PROJECTED_FIELDS)


def test_shared_comments_include_only_feedback_fields_and_are_newest_first():
    rows = [record("account-a", name="first", comment="Older comment.", reasons=["unclear"]),
            record("account-b", name="second", rating=2, comment="Newer comment.",
                   when=NOW + timedelta(seconds=1))]
    client, _ = storage(rows)
    report = FeedbackSummaryService(client).read()
    assert [entry.comment for entry in report.comments] == ["Newer comment.", "Older comment."]
    assert report.comments[1].reasons == ["Unclear"]
    assert set(report.comments[0].model_dump()) == {"comment", "rating", "helpful", "reasons"}
    assert report.comment_count == 2
    for forbidden in ("PRIVATE_CHAT", "PRIVATE_CHILD", "account-a", "account-b", "recorded_at", "conversations"):
        assert forbidden not in report.model_dump_json()


def test_comment_list_is_bounded_without_truncating_rating_counts():
    rows = [record("one", name=str(i), comment=f"Comment {i}.",
                   when=NOW - timedelta(seconds=i)) for i in range(52)]
    client, _ = storage(rows)
    report = FeedbackSummaryService(client).read()
    assert len(report.comments) == 50
    assert report.comment_count == report.ratings[3].count == 52
    assert report.comments[0].comment == "Comment 0."
    assert report.comments[-1].comment == "Comment 49."


@pytest.mark.parametrize("comment", [None, "", "  ", "x" * 501, {"text": "not a string"}])
def test_blank_or_malformed_comments_do_not_break_rating_counts(comment):
    client, _ = storage([record("one", comment=comment)])
    report = FeedbackSummaryService(client).read()
    assert report.ratings[3].count == 1
    assert report.comments == []
    assert report.comment_count == 0


def test_editing_saved_feedback_moves_its_contribution_instead_of_adding_a_second_one():
    original, _ = storage([record("one", rating=2, reasons=["unclear"], comment="Original comment.")])
    before = FeedbackSummaryService(original).read()
    assert before.ratings[1].count == 1
    assert before.reasons[0].count == 1
    updated, _ = storage([record("one", rating=5, comment="Updated comment.", when=NOW + timedelta(seconds=1))])
    after = FeedbackSummaryService(updated).read()
    assert after.ratings[1].count == 0
    assert after.ratings[4].count == 1
    assert after.reasons[0].count == 0
    assert [entry.comment for entry in after.comments] == ["Updated comment."]


def test_numeric_ratings_are_not_counted_again_as_historical_binary_feedback():
    result = summarize_feedback([{"rating": 5, "helpful": True}, {"rating": None, "helpful": True}])
    assert result.ratings[4].count == 1
    assert result.legacy_helpfulness[0].count == 1


@pytest.mark.parametrize("accepted", [
    {}, {"consent_version": "2026-10-24.1", "consent_at": NOW - timedelta(days=1), "caregiver_authority": True},
    {"consent_version": "2026-10-26.1", "consent_at": NOW - timedelta(days=1), "caregiver_authority": True},
    {"consent_version": CONSENT_VERSION, "consent_at": NOW + timedelta(seconds=1), "caregiver_authority": True},
    {"consent_version": CONSENT_VERSION, "consent_at": NOW, "caregiver_authority": False},
])
def test_unaccepted_or_pre_notice_feedback_is_not_repurposed(accepted):
    rows = [record(f"u{i}") for i in range(5)]
    client, _ = storage(rows, accepted={f"u{i}": accepted for i in range(5)})
    report = FeedbackSummaryService(client).read()
    assert report.ratings[3].count == 0
    assert report.comments == []


def test_deleted_feedback_is_absent_without_a_separate_export_to_clean_up():
    client, _ = storage([record(f"u{i}") for i in range(5)])
    assert FeedbackSummaryService(client).read().ratings[3].count == 5
    after, _ = storage([record(f"u{i}") for i in range(4)])
    assert FeedbackSummaryService(after).read().ratings[3].count == 4
    assert FeedbackSummaryService(storage()[0]).read().comments == []
    client.batch.assert_not_called()
    client.transaction.assert_not_called()


def test_scan_limit_fails_instead_of_publishing_partial_statistics(monkeypatch):
    monkeypatch.setattr("backend.services.feedback_summary.MAX_DOCUMENTS_PER_GROUP", 2)
    client, _ = storage([record(f"u{i}") for i in range(3)])
    with pytest.raises(RuntimeError, match="scan limit"):
        FeedbackSummaryService(client).read()


def test_account_budget_fails_instead_of_publishing_partial_statistics(monkeypatch):
    monkeypatch.setattr("backend.services.feedback_summary.MAX_ACCOUNTS", 2)
    client, _ = storage([record(f"u{i}") for i in range(3)])
    with pytest.raises(RuntimeError, match="account limit"):
        FeedbackSummaryService(client).read()


def test_time_budget_fails_without_publishing_partial_statistics(monkeypatch):
    ticks = iter([0, 11])
    monkeypatch.setattr("backend.services.feedback_summary.time.perf_counter", lambda: next(ticks))
    client, _ = storage()
    with pytest.raises(RuntimeError, match="time budget"):
        FeedbackSummaryService(client).read()


@pytest.mark.parametrize("value", [True, "5", 6, 0, None])
def test_malformed_numeric_feedback_does_not_count(value):
    client, _ = storage([record(f"u{i}", rating=value) for i in range(5)])
    assert all(bucket.count == 0 for bucket in FeedbackSummaryService(client).read().ratings)


def test_noncanonical_paths_and_user_messages_are_not_aggregated():
    rows = [record(f"u{i}") for i in range(5)]
    rows[0].reference.path = "other/u0/messages/a"
    rows[1].to_dict = lambda: {"role": "user", "feedback": {"rating": 4, "recorded_at": NOW}}
    client, _ = storage(rows)
    assert FeedbackSummaryService(client).read().ratings[3].count == 3


def claims(permission=False):
    return {"uid": "administrator", "email_verified": True,
            "firebase": {"sign_in_second_factor": "totp"},
            "feedback_summary_admin": permission}


@pytest.fixture
def admin_storage(client):
    from backend.core.security import get_account_security_service

    previous = app.dependency_overrides.copy()
    client.app.dependency_overrides[get_account_security_service]().read.return_value = {
        "mfa_enabled": True, "mfa_required": False, "feedback_summary_admin": True,
    }
    service = MagicMock()
    app.dependency_overrides[get_caregiver_data_service] = lambda: service
    try:
        yield service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.parametrize("permission", [False, None, "true", 1])
def test_ordinary_accounts_and_nonboolean_claims_cannot_read_summaries(client, admin_storage, permission):
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(permission)):
        response = client.get("/admin/feedback/summary", headers={"Authorization": "Bearer test"})
        assert response.status_code == 403
        access = client.get("/admin/feedback/access", headers={"Authorization": "Bearer test"})
        assert access.json() == {"allowed": False}
    admin_storage.client.collection_group.assert_not_called()


def test_no_token_cannot_read_summary(client, admin_storage):
    assert client.get("/admin/feedback/summary").status_code == 401
    admin_storage.client.collection_group.assert_not_called()


def test_revoked_current_role_denies_a_previously_issued_administrator_token(client, admin_storage):
    from backend.core.security import get_account_security_service

    security = client.app.dependency_overrides[get_account_security_service]()
    security.read.return_value["feedback_summary_admin"] = False
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)):
        headers = {"Authorization": "Bearer old-admin-token"}
        assert client.get("/admin/feedback/summary", headers=headers).status_code == 403
        assert client.get("/admin/feedback/access", headers=headers).json() == {"allowed": False}
    admin_storage.client.collection_group.assert_not_called()


def test_administrator_needs_completed_mfa_before_reading_feedback(client, admin_storage):
    first_factor = {**claims(True), "firebase": {"sign_in_provider": "google.com"}}
    with patch("backend.core.security.auth.verify_id_token", return_value=first_factor):
        response = client.get("/admin/feedback/summary", headers={"Authorization": "Bearer first-factor-token"})
    assert response.status_code == 403
    admin_storage.client.collection_group.assert_not_called()


def test_admin_receives_only_summary_and_cannot_request_raw_rows_or_filters(client, admin_storage):
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)), \
            patch("backend.api.v1.endpoints.admin.FeedbackSummaryService.read", return_value=summarize_feedback([])) as read:
        headers = {"Authorization": "Bearer test"}
        response = client.get("/admin/feedback/summary", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"unit", "ratings", "reasons", "legacy_helpfulness", "comments", "comment_count"}
        assert client.get("/admin/feedback/access", headers=headers).json() == {"allowed": True}
        assert client.get("/admin/feedback/summary?uid=other", headers=headers).status_code == 422
        assert client.get("/admin/feedback/records", headers=headers).status_code == 404
        read.assert_called_once()


def test_storage_failure_does_not_return_zero_counts_or_exception_content(client, admin_storage):
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)), \
            patch("backend.api.v1.endpoints.admin.FeedbackSummaryService.read", side_effect=RuntimeError("PRIVATE")):
        response = client.get("/admin/feedback/summary", headers={"Authorization": "Bearer test"})
        assert response.status_code == 503
        assert "PRIVATE" not in response.text
        assert "ratings" not in response.json()


def test_administrator_role_cannot_open_private_conversations(client, admin_storage):
    admin_storage.get_conversation.return_value = None
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)):
        response = client.get("/conversations/another-account-chat", headers={"Authorization": "Bearer test"})
    assert response.status_code == 403
    admin_storage.get_conversation.assert_not_called()


@pytest.mark.parametrize("method,path,payload", [
    ("get", "/children", None),
    ("post", "/children", {"name": "Example child", "date_of_birth": "2026-10-15"}),
    ("post", "/coach", {"child_id": "example", "question": "Play ideas?"}),
    ("get", "/conversations?child_id=example", None),
    ("post", "/speech/transcribe", None),
])
def test_administrator_accounts_cannot_use_caregiver_features(client, admin_storage, method, path, payload):
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)):
        response = getattr(client, method)(path, headers={"Authorization": "Bearer administrator-token"},
                                           **({"json": payload} if payload is not None else {}))
    assert response.status_code == 403
    assert "caregiver account" in response.json()["detail"]
    admin_storage.get_child.assert_not_called()
    admin_storage.create_child.assert_not_called()
    admin_storage.get_conversation.assert_not_called()


def test_current_account_exposes_its_authoritative_role(client, admin_storage):
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)):
        response = client.get("/me", headers={"Authorization": "Bearer administrator-token"})
    assert response.json() == {"uid": "administrator", "role": "administrator"}


def test_role_preview_never_connects_to_firebase():
    with patch("scripts.set_feedback_admin.initialize_firebase") as initialize:
        main(["--uid", "example", "--grant"])
        initialize.assert_not_called()


@pytest.mark.parametrize("grant", [True, False])
def test_role_update_preserves_other_claims_and_revokes_existing_sessions(grant):
    account = SimpleNamespace(disabled=False, email_verified=True,
                              custom_claims={"unrelated_permission": "keep", "feedback_summary_admin": True})
    with patch("scripts.set_feedback_admin.auth.get_user", return_value=account), \
            patch("scripts.set_feedback_admin.auth.set_custom_user_claims") as save, \
            patch("scripts.set_feedback_admin.auth.revoke_refresh_tokens") as revoke:
        update_permission("example", grant=grant, app="app")
        expected = {"unrelated_permission": "keep", **({"feedback_summary_admin": True} if grant else {})}
        save.assert_called_once_with("example", expected, app="app")
        revoke.assert_called_once_with("example", app="app")


@pytest.mark.parametrize("disabled,verified", [(True, True), (False, False)])
def test_grant_rejects_disabled_or_unverified_accounts(disabled, verified):
    account = SimpleNamespace(disabled=disabled, email_verified=verified, custom_claims={})
    with patch("scripts.set_feedback_admin.auth.get_user", return_value=account), \
            patch("scripts.set_feedback_admin.auth.set_custom_user_claims") as save:
        with pytest.raises(ValueError, match="enabled account with verified email"):
            update_permission("example", grant=True, app="app")
        save.assert_not_called()
