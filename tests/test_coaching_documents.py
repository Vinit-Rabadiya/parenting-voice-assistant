"""Real coaching dependencies and storage reads, with only SDK IO replaced."""
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import Client, DocumentSnapshot
import pytest

from backend.api.coaching_context import prepare_coaching_documents
from backend.api.consent import require_processing_consent
from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.config import settings
from backend.core.privacy import CONSENT_VERSION
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingResult


@pytest.fixture
def batched_coach(client, monkeypatch):
    from types import SimpleNamespace

    database = Client(project="offline-test", credentials=AnonymousCredentials())
    now = datetime.now(timezone.utc)
    records = {
        "users/caregiver": {"consent_version": CONSENT_VERSION, "consent_at": now, "caregiver_authority": True},
        "users/caregiver/children/child-1": {"name": "Example", "date_of_birth": date(2026, 5, 4), "created_at": now},
        "users/caregiver/conversations/chat-1": {"child_id": "child-1", "title": "Example", "created_at": now, "updated_at": now},
    }

    def get_all(references, **kwargs):
        return [DocumentSnapshot(ref, records.get(ref.path), exists=ref.path in records,
                                 read_time=now, create_time=now, update_time=now) for ref in reversed(references)]

    database.get_all = Mock(side_effect=get_all)
    data = CaregiverDataService(database)
    data.save_conversation_turn = Mock(return_value="answer-1")
    data.get_child = Mock(side_effect=AssertionError("The batched profile must be reused"))
    data.get_consent = Mock(side_effect=AssertionError("The batched consent must be reused"))
    coaching, retrieval = Mock(), Mock()
    coaching.generate.return_value = CoachingResult("Talk gently with your baby.", [], answer_basis="general_information")
    retrieval.retrieve.return_value = []
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr("backend.services.caregiver_data.current_date", lambda: date(2026, 11, 4))
    for dependency in (prepare_coaching_documents, require_processing_consent):
        monkeypatch.delitem(client.app.dependency_overrides, dependency, raising=False)
    monkeypatch.setitem(client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    monkeypatch.setitem(client.app.dependency_overrides, get_coaching_service, lambda: coaching)
    monkeypatch.setitem(client.app.dependency_overrides, get_retrieval_service, lambda: retrieval)
    # Every possible unbatched document read is an error; queries remain bounded.
    with patch("google.cloud.firestore_v1.document.DocumentReference.get", side_effect=AssertionError("Unbatched read")), \
         patch("google.cloud.firestore_v1.query.Query.stream", return_value=[]) as stream, \
         patch("backend.core.security.auth.verify_id_token", return_value={
             "uid": "caregiver", "email_verified": True, "exp": now.timestamp() + 3600,
             "auth_time": now.timestamp(), "firebase": {}}):
        yield SimpleNamespace(client=client, database=database, records=records, data=data,
                              coaching=coaching, stream=stream,
                              headers={"Authorization": "Bearer offline-token"})
    database.close()


def post(c, path="/coach", **changes):
    return c.client.post(path, headers=c.headers,
                         json={"child_id": "child-1", "conversation_id": "chat-1",
                               "question": "How can I talk with my baby?", **changes})


@pytest.mark.parametrize("path", ["/coach", "/api/v1/coach"])
def test_one_fresh_batch_and_one_messages_query_per_turn(batched_coach, path):
    c = batched_coach
    for _ in range(2):
        response = post(c, path)
        assert response.status_code == 200
        assert response.json()["conversation_id"] == "chat-1"
    assert c.database.get_all.call_count == c.stream.call_count == 2
    for call in c.database.get_all.call_args_list:
        assert [ref.path for ref in call.args[0]] == ["users/caregiver", "users/caregiver/children/child-1",
                                                     "users/caregiver/conversations/chat-1"]
        assert call.kwargs == {"field_paths": None, "transaction": None}
    assert c.data.save_conversation_turn.call_count == 2


def test_withdrawn_consent_is_fresh_and_stops_profile_interpretation_and_message_reads(batched_coach):
    c = batched_coach
    assert post(c).status_code == 200
    c.records["users/caregiver"]["caregiver_authority"] = False
    with patch.object(c.data, "_child_response", side_effect=AssertionError("No profile use before consent")):
        response = post(c)
    assert response.status_code == 403
    assert response.headers["X-Consent-Required"] == "true"
    assert c.database.get_all.call_count == 2
    assert c.stream.call_count == 1


def test_profile_changes_are_fetched_again_for_the_next_message(batched_coach):
    c = batched_coach
    assert post(c).json()["child_age_months"] == 6
    c.records["users/caregiver/children/child-1"]["date_of_birth"] = date(2026, 8, 4)
    assert post(c).json()["child_age_months"] == 3
    assert c.database.get_all.call_count == 2


def test_first_turn_batches_only_consent_and_profile_before_creating_conversation(batched_coach):
    from uuid import uuid4

    c = batched_coach
    identifier = str(uuid4())
    c.data.create_conversation = Mock(return_value={"id": identifier, "child_id": "child-1"})
    response = post(c, conversation_id=identifier, start_conversation=True)
    assert response.status_code == 200
    assert response.json()["conversation_id"] == identifier
    assert len(c.database.get_all.call_args.args[0]) == 2
    c.stream.assert_not_called()
    c.data.create_conversation.assert_called_once_with("caregiver", "child-1", conversation_id=identifier)


@pytest.mark.parametrize("change", ["missing", "different_child", "deleting"])
def test_unavailable_parent_cannot_read_messages(batched_coach, change):
    c = batched_coach
    key = "users/caregiver/conversations/chat-1"
    if change == "missing":
        del c.records[key]
    elif change == "different_child":
        c.records[key]["child_id"] = "other-child"
    else:
        c.records[key]["deleting"] = True
    assert post(c).status_code == 404
    c.stream.assert_not_called()
    c.coaching.generate.assert_not_called()


def test_missing_child_still_requires_owned_profile_before_generation(batched_coach):
    c = batched_coach
    del c.records["users/caregiver/children/child-1"]
    assert post(c).status_code == 404
    c.coaching.generate.assert_not_called()


def test_urgent_response_does_not_query_history(batched_coach):
    c = batched_coach
    response = post(c, question="My baby is not breathing")
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    c.stream.assert_not_called()
    c.coaching.generate.assert_not_called()


@pytest.mark.parametrize("failure", ["duplicate", "missing", "foreign", "unavailable"])
def test_invalid_batch_replies_fail_closed_without_family_details(batched_coach, failure):
    c = batched_coach
    original = c.database.get_all.side_effect

    def invalid(references, **kwargs):
        snapshots = original(references, **kwargs)
        if failure == "duplicate":
            return [*snapshots, snapshots[0]]
        if failure == "missing":
            return snapshots[1:]
        if failure == "foreign":
            snapshots[0]._reference = c.database.document("users/another-account")
            return snapshots
        raise RuntimeError("PRIVATE_DATABASE_DETAILS")

    c.database.get_all.side_effect = invalid
    response = post(c)
    assert response.status_code == 503
    assert "PRIVATE_DATABASE_DETAILS" not in response.text
    c.stream.assert_not_called()
    c.coaching.generate.assert_not_called()


def test_prefetched_header_cannot_be_reused_for_another_conversation(batched_coach):
    c = batched_coach
    documents = c.data.get_coaching_documents("caregiver", "child-1", "chat-1")
    with pytest.raises(ValueError, match="snapshot"):
        c.data.get_conversation("caregiver", "other-chat", expected_child_id="child-1",
                                prefetched_snapshot=documents["conversation_snapshot"])
    c.stream.assert_not_called()
