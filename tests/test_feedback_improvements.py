"""Review-stage gates, administrator isolation, stale writes and deletion."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError
import pytest

from backend.api.dependencies import get_caregiver_data_service
from backend.core.security import get_account_security_service
from backend.schemas.feedback_improvements import ImprovementContent
from backend.services.feedback_improvements import (
    FeedbackImprovementService, ImprovementConflict, ImprovementNotFound, ImprovementStageError,
)


LEGACY_DATES = {"fictional_date_of_birth": "2026-05-10", "evaluation_date": "2026-11-10"}


def draft(**changes):
    return {"title": "Repeated alternatives", "category": "repeated_advice",
            "scenario": "A fictional caregiver asks for another play idea after receiving two suggestions.",
            "expected_behavior": "Offer a distinct source-supported action or explain the limitation.",
            "fictional_confirmed": True, **changes}


def reviewed(status="ready_for_release", **changes):
    baseline = {"answer": "Repeat the earlier activity.", "model": "test-model", "prompt_revision": "before",
                "corpus_revision": "corpus-v1", "report_reference": "run-baseline.json",
                "scores": {"faithfulness": 4, "helpfulness": 2, "age_fit": 4, "clarity": 3, "safety": 4}}
    candidate = {**baseline, "answer": "Offer a distinct reviewed activity.", "prompt_revision": "after",
                 "report_reference": "run-candidate.json", "scores": {**baseline["scores"], "helpfulness": 4}}
    return draft(status=status, baseline=baseline, candidate=candidate, change_area="prompt",
                 change_summary="Clarify how follow-up alternatives differ from prior actions.",
                 change_reference="synthetic-change-reference", evaluation_notes="Compared the same fictional case and reviewed the recorded regressions.",
                 checks={key: True for key in ("issue_resolved", "sources_checked", "age_checked", "safety_checked", "regressions_passed")},
                 **changes)


class Document:
    def __init__(self, store, path):
        self.store, self.path, self.id = store, path, path.split("/")[-1]

    def collection(self, name):
        return Collection(self.store, f"{self.path}/{name}")

    def get(self, **kwargs):
        self.store.reads.append(self.path)
        value = deepcopy(self.store.rows.get(self.path))
        return SimpleNamespace(id=self.id, reference=self, exists=value is not None, to_dict=lambda: value)

    def create(self, value, **kwargs):
        assert self.path not in self.store.rows
        self.store.rows[self.path] = deepcopy(value)


class Collection:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.maximum, self.cursor = None, None

    def document(self, identifier):
        return Document(self.store, f"{self.path}/{identifier}")

    def order_by(self, *args, **kwargs):
        return self

    def start_after(self, snapshot):
        self.cursor = snapshot.reference.path
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def stream(self, **kwargs):
        paths = [path for path in self.store.rows if path.rsplit("/", 1)[0] == self.path]
        paths.sort(key=lambda path: self.store.rows[path]["updated_at"], reverse=True)
        if self.cursor:
            paths = paths[paths.index(self.cursor) + 1:]
        return iter(Document(self.store, path).get() for path in paths[:self.maximum])


class MemoryFirestore:
    def __init__(self):
        self.rows, self.reads = {}, []

    def collection(self, name):
        return Collection(self, name)

    def transaction(self):
        return self

    def set(self, document, value):
        self.rows[document.path] = deepcopy(value)

    def delete(self, document):
        del self.rows[document.path]


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr("backend.services.feedback_improvements.firestore.transactional", lambda function: function)
    return MemoryFirestore()


@pytest.mark.parametrize("changes", [
    {"fictional_confirmed": False}, {"fictional_confirmed": "yes"},
    {**LEGACY_DATES, "evaluation_date": "2026-05-09"},
    {**LEGACY_DATES, "evaluation_date": "2029-01-01"},
    {"evaluation_date": LEGACY_DATES["evaluation_date"]},
    {"caregiver_uid": "private-account"}, {"category": "unknown"},
])
def test_invalid_or_nonfictional_case_is_rejected(changes):
    with pytest.raises(ValidationError):
        ImprovementContent.model_validate(draft(**changes))


@pytest.mark.parametrize("change", ["missing_capture", "missing_score", "missing_check", "regression", "missing_evidence"])
def test_recording_evaluation_requires_complete_checks_and_no_safety_regression(change):
    value = reviewed()
    if change == "missing_capture":
        value["baseline"]["answer"] = ""
    elif change == "missing_score":
        value["candidate"]["scores"]["safety"] = None
    elif change == "missing_check":
        value["checks"]["regressions_passed"] = False
    elif change == "regression":
        value["candidate"]["scores"]["safety"] = 2
    else:
        value["candidate"]["report_reference"] = ""
    with pytest.raises(ValidationError):
        ImprovementContent.model_validate(value)


def test_release_needs_deployed_revision_and_explicit_observation():
    with pytest.raises(ValidationError):
        ImprovementContent.model_validate(reviewed(status="released"))
    assert ImprovementContent.model_validate(reviewed(status="released", release_revision="a" * 40,
                                                       deployment_checked=True, release_notes="Deployment checked with the fictional reproduction case."))


def test_source_support_can_be_explicitly_not_applicable_without_inventing_a_score():
    value = reviewed()
    for side in ("baseline", "candidate"):
        value[side].update(faithfulness_not_applicable=True, faithfulness_note="No excerpts supplied for this fixed boundary response.")
        value[side]["scores"]["faithfulness"] = None
    assert ImprovementContent.model_validate(value)
    value["candidate"]["faithfulness_note"] = ""
    with pytest.raises(ValidationError):
        ImprovementContent.model_validate(value)


def test_a_low_safety_score_cannot_be_approved_just_because_it_did_not_regress():
    value = reviewed()
    value["baseline"]["scores"]["safety"] = value["candidate"]["scores"]["safety"] = 1
    with pytest.raises(ValidationError):
        ImprovementContent.model_validate(value)


@pytest.mark.parametrize("dates", [{}, LEGACY_DATES], ids=["without-dates", "legacy-dates"])
def test_owned_case_lifecycle_requires_evaluation_and_records_release(store, dates):
    service = FeedbackImprovementService(store)
    first = service.create("admin-a", ImprovementContent.model_validate(draft(**dates)))
    assert first.version == 1 and first.released_at is None
    with pytest.raises(ImprovementStageError):
        service.update("admin-a", first.id, 1, ImprovementContent.model_validate(reviewed(status="released",
            release_revision="a" * 40, deployment_checked=True, release_notes="Deployed correction verified.")))
    checked = service.update("admin-a", first.id, 1, ImprovementContent.model_validate(reviewed(**dates)))
    released = service.update("admin-a", first.id, 2, checked.content.model_copy(update={"status": "released",
        "release_revision": "a" * 40, "deployment_checked": True, "release_notes": "Deployed correction verified."}))
    assert released.version == 3 and released.released_at is not None
    saved = service.list("admin-a")["items"][0].content.model_dump(mode="json")
    assert {key: saved[key] for key in LEGACY_DATES} == {key: dates.get(key) for key in LEGACY_DATES}
    with pytest.raises(ImprovementStageError):
        service.update("admin-a", first.id, 3, released.content.model_copy(update={"release_revision": "b" * 40}))
    with pytest.raises(ImprovementStageError):
        service.update("admin-a", first.id, 3, released.content.model_copy(update={"scenario": "Changed reviewed scenario"}))
    reopened = service.update("admin-a", first.id, 3, released.content.model_copy(update={"status": "investigating"}))
    assert not any(reopened.content.checks.model_dump().values())
    assert reopened.content.release_revision == "" and reopened.released_at is None


def test_stale_writes_and_deletes_cannot_overwrite_a_new_review(store):
    service = FeedbackImprovementService(store)
    item = service.create("admin-a", ImprovementContent.model_validate(draft()))
    service.update("admin-a", item.id, 1, item.content.model_copy(update={"title": "New title"}))
    with pytest.raises(ImprovementConflict):
        service.update("admin-a", item.id, 1, item.content)
    with pytest.raises(ImprovementConflict):
        service.delete("admin-a", item.id, 1)
    assert service.list("admin-a")["items"][0].content.title == "New title"


def test_two_administrators_cannot_list_mutate_or_use_each_others_cursor(store):
    service = FeedbackImprovementService(store)
    item = service.create("admin-a", ImprovementContent.model_validate(draft()))
    assert service.list("admin-b")["items"] == []
    for operation in (lambda: service.update("admin-b", item.id, 1, item.content),
                      lambda: service.delete("admin-b", item.id, 1),
                      lambda: service.list("admin-b", before=item.id)):
        with pytest.raises(ImprovementNotFound):
            operation()
    assert all("/feedback_improvements/" in path for path in store.reads)


def test_case_pagination_and_deletion_do_not_copy_caregiver_records(store):
    service = FeedbackImprovementService(store)
    older = service.create("admin-a", ImprovementContent.model_validate(draft()))
    newer = service.create("admin-a", ImprovementContent.model_validate(draft(title="Second case")))
    first = service.list("admin-a", limit=1)
    assert first["items"][0].id == newer.id and first["next_cursor"] == newer.id
    second = service.list("admin-a", limit=1, before=first["next_cursor"])
    assert second["items"][0].id == older.id and second["next_cursor"] is None
    service.delete("admin-a", older.id, 1)
    assert len(store.rows) == 1


@pytest.fixture
def review_api(client, store, monkeypatch):
    security = client.app.dependency_overrides[get_account_security_service]()
    security.read.return_value = {"mfa_enabled": True, "mfa_required": False, "feedback_summary_admin": True}
    data = Mock(client=store)
    monkeypatch.setitem(client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    token = Mock(return_value={"uid": "admin-a", "email_verified": True,
                             "firebase": {"sign_in_second_factor": "totp"}, "feedback_summary_admin": True})
    monkeypatch.setattr("backend.core.security.auth.verify_id_token", token)
    client.headers.update({"Authorization": "Bearer test-token"})
    return SimpleNamespace(client=client, token=token, data=data, store=store, security=security)


def test_api_create_update_list_delete_uses_only_authenticated_administrator(review_api):
    api = review_api.client
    created = api.post("/admin/feedback/improvements", json={"content": draft()})
    assert created.status_code == 201, created.text
    item = created.json()
    assert created.headers["cache-control"] == "no-store" and "uid" not in item
    changed = api.put(f"/admin/feedback/improvements/{item['id']}", json={"expected_version": 1, "content": reviewed()})
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert api.put(f"/admin/feedback/improvements/{item['id']}", json={"expected_version": 1, "content": draft()}).status_code == 409
    listed = api.get("/admin/feedback/improvements")
    assert listed.json()["items"][0]["content"]["status"] == "ready_for_release"
    assert api.get("/admin/feedback/improvements?uid=someone").status_code == 422
    assert api.delete(f"/admin/feedback/improvements/{item['id']}?expected_version=2").status_code == 204
    review_api.data.get_child.assert_not_called()
    review_api.data.get_conversation.assert_not_called()


def test_api_records_verified_release_from_investigation_and_can_reopen_it(review_api):
    api = review_api.client
    item = api.post("/admin/feedback/improvements", json={"content": draft()}).json()
    path = f"/admin/feedback/improvements/{item['id']}"
    correction = {**item["content"], "status": "released", "release_without_evaluation": True,
                  "release_revision": "a" * 40, "release_notes": "Correction checked on the live app."}
    assert api.put(path, json={"expected_version": 1, "content": correction}).status_code == 422
    released = api.put(path, json={"expected_version": 1, "content": {**correction, "deployment_checked": True}})
    assert released.status_code == 200, released.text
    saved = released.json()
    assert saved["version"] == 2 and saved["released_at"]
    assert saved["content"]["status"] == "released" and saved["content"]["release_without_evaluation"] is True
    assert saved["content"]["baseline"]["answer"] == "" and not any(saved["content"]["checks"].values())
    assert api.get("/admin/feedback/improvements").json()["items"] == [saved]
    reopened = api.put(path, json={"expected_version": 2, "content": {
        **saved["content"], "status": "investigating", "release_without_evaluation": False,
    }}).json()
    assert reopened["released_at"] is None and reopened["content"]["release_revision"] == ""
    assert not reopened["content"]["deployment_checked"]


@pytest.mark.parametrize("change", ["role", "revoked", "mfa", "signed_out"])
def test_administrator_authorization_is_required_for_reads_and_writes(review_api, change):
    if change == "role":
        review_api.token.return_value["feedback_summary_admin"] = False
    elif change == "revoked":
        review_api.security.read.return_value["feedback_summary_admin"] = False
    elif change == "mfa":
        review_api.token.return_value["firebase"] = {}
    else:
        review_api.client.headers.pop("Authorization")
    expected = 401 if change == "signed_out" else 403
    assert review_api.client.get("/admin/feedback/improvements").status_code == expected
    assert review_api.client.post("/admin/feedback/improvements", json={"content": draft()}).status_code == expected
    assert review_api.store.rows == {}


def test_api_storage_failure_does_not_publish_private_exception_text(review_api):
    with patch("backend.api.v1.endpoints.admin.FeedbackImprovementService.list", side_effect=RuntimeError("PRIVATE_CONTENT")):
        response = review_api.client.get("/admin/feedback/improvements")
    assert response.status_code == 503 and "PRIVATE_CONTENT" not in response.text


def test_invalid_stage_and_private_link_fields_cannot_be_created(review_api):
    response = review_api.client.post("/admin/feedback/improvements", json={"content": draft(), "caregiver_uid": "someone"})
    assert response.status_code == 422
    response = review_api.client.post("/admin/feedback/improvements", json={"content": reviewed()})
    assert response.status_code == 409
