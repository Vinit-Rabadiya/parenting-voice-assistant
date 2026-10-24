"""Aggregate privacy checks use synthetic records, never real conversations."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.api.dependencies import get_caregiver_data_service
from backend.core.privacy import CONSENT_VERSION
from backend.main import app
from backend.services.feedback_summary import (
    FeedbackSummaryService, MAX_DOCUMENTS_PER_GROUP, PROJECTED_FIELDS, summarize_feedback,
)
from scripts.set_feedback_admin import main, update_permission

NOW = datetime.now(timezone.utc) - timedelta(minutes=1)


def record(uid, *, name="a", rating=4, helpful=None, reasons=None, group="messages", when=NOW):
    path = (f"users/{uid}/conversations/chat/messages/{name}" if group == "messages"
            else f"users/{uid}/interactions/{name}")
    return SimpleNamespace(reference=SimpleNamespace(path=path), to_dict=lambda: {
        "role": "assistant", "text": "PRIVATE_CHAT", "child_id": "PRIVATE_CHILD",
        "feedback": {"rating": rating, "helpful": helpful, "reasons": reasons or [],
                     "comment": "PRIVATE_COMMENT", "recorded_at": when},
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
        snapshot = SimpleNamespace(exists=bool(value), to_dict=lambda: value)
        return SimpleNamespace(get=lambda **kwargs: snapshot)

    client.collection.return_value.document.side_effect = account
    return client, queries


@pytest.mark.parametrize("count,bounds", [(0, (None, None)), (4, (None, None)),
                                         (5, (5, 9)), (9, (5, 9)), (10, (10, 14))])
def test_small_groups_are_suppressed_and_counts_are_coarse(count, bounds):
    result = summarize_feedback({f"account-{i}": {"rating": 4} for i in range(count)})
    bucket = result.ratings[3]
    assert (bucket.lower, bucket.upper) == bounds
    assert result.ratings[0].lower is None
    assert "total" not in result.model_dump()


def test_one_caregiver_cannot_create_a_reportable_group_by_repeated_feedback():
    client, _ = storage([record("one", name=str(i)) for i in range(20)])
    assert FeedbackSummaryService(client).read().ratings[3].lower is None


def test_synthetic_improvement_signal_contains_only_grouped_categories():
    result = summarize_feedback({f"synthetic-{i}": {"rating": 2, "reasons": ["did_not_answer"]}
                                 for i in range(5)})
    assert result.ratings[1].lower == 5
    assert result.reasons[2].lower == 5
    assert "synthetic" not in result.model_dump_json()
    assert all(bucket.lower is None for bucket in result.legacy_helpfulness)


def test_latest_feedback_per_caregiver_and_legacy_scale_remain_separate():
    rows = [record(f"u{i}", name="old", rating=1) for i in range(5)]
    rows += [record(f"u{i}", name="new", rating=5, reasons=["unclear"],
                    when=NOW + timedelta(seconds=1)) for i in range(5)]
    legacy = [record(f"legacy{i}", rating=None, helpful=False, group="interactions") for i in range(5)]
    client, queries = storage(rows, legacy)
    result = FeedbackSummaryService(client).read()
    assert result.ratings[0].lower is None
    assert result.ratings[4].lower == 5
    assert result.reasons[0].lower == 5
    assert result.legacy_helpfulness[0].lower is None
    assert result.legacy_helpfulness[1].lower == 5
    payload = result.model_dump_json()
    for forbidden in ("PRIVATE", "comment", "child_id", "recorded_at", "u0", "legacy0"):
        assert forbidden not in payload
    for query in queries.values():
        query.select.assert_called_once_with(PROJECTED_FIELDS)
        query.limit.assert_called_once_with(MAX_DOCUMENTS_PER_GROUP + 1)
    assert not any("comment" in field or "text" in field for field in PROJECTED_FIELDS)


@pytest.mark.parametrize("accepted", [
    {}, {"consent_version": "old", "consent_at": NOW - timedelta(days=1), "caregiver_authority": True},
    {"consent_version": CONSENT_VERSION, "consent_at": NOW + timedelta(seconds=1), "caregiver_authority": True},
    {"consent_version": CONSENT_VERSION, "consent_at": NOW, "caregiver_authority": False},
])
def test_unaccepted_or_pre_notice_feedback_is_not_repurposed(accepted):
    rows = [record(f"u{i}") for i in range(5)]
    client, _ = storage(rows, accepted={f"u{i}": accepted for i in range(5)})
    assert FeedbackSummaryService(client).read().ratings[3].lower is None


def test_deleted_feedback_is_absent_without_a_separate_export_to_clean_up():
    client, _ = storage([record(f"u{i}") for i in range(5)])
    assert FeedbackSummaryService(client).read().ratings[3].lower == 5
    after, _ = storage([record(f"u{i}") for i in range(4)])
    assert FeedbackSummaryService(after).read().ratings[3].lower is None
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
    assert all(bucket.lower is None for bucket in FeedbackSummaryService(client).read().ratings)


def test_noncanonical_paths_and_user_messages_are_not_aggregated():
    rows = [record(f"u{i}") for i in range(5)]
    rows[0].reference.path = "other/u0/messages/a"
    rows[1].to_dict = lambda: {"role": "user", "feedback": {"rating": 4, "recorded_at": NOW}}
    client, _ = storage(rows)
    assert FeedbackSummaryService(client).read().ratings[3].lower is None


def claims(permission=False):
    return {"uid": "administrator", "email_verified": True,
            "firebase": {"sign_in_second_factor": "totp"},
            "feedback_summary_admin": permission}


@pytest.fixture
def admin_storage(client):
    previous = app.dependency_overrides.copy()
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


def test_admin_receives_only_summary_and_cannot_request_raw_rows_or_filters(client, admin_storage):
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)), \
            patch("backend.api.v1.endpoints.admin.FeedbackSummaryService.read", return_value=summarize_feedback({})) as read:
        headers = {"Authorization": "Bearer test"}
        response = client.get("/admin/feedback/summary", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"unit", "minimum_group_size", "ratings", "reasons", "legacy_helpfulness"}
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


def test_administrator_permission_does_not_bypass_private_conversation_ownership(client, admin_storage):
    admin_storage.get_conversation.return_value = None
    with patch("backend.core.security.auth.verify_id_token", return_value=claims(True)):
        response = client.get("/conversations/another-account-chat", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404
    admin_storage.get_conversation.assert_called_once_with("administrator", "another-account-chat", 50, None)


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
