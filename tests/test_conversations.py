"""Conversation routes use authenticated ownership and bounded history reads."""

from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import MagicMock
from google.api_core.exceptions import FailedPrecondition

import pytest

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingResult
from backend.services.retrieval import RetrievalService, RetrievedPassage
from backend.services.response_safety import SAFE_RESPONSE


@pytest.fixture
def history_service(client):
    service = MagicMock()
    app.dependency_overrides[require_authenticated_user] = lambda: {"uid": "account-a"}
    app.dependency_overrides[get_caregiver_data_service] = lambda: service
    yield service
    app.dependency_overrides.pop(require_authenticated_user, None)
    app.dependency_overrides.pop(get_caregiver_data_service, None)


def conversation():
    now = datetime.now(timezone.utc)
    return {"id": "chat-1", "child_id": "child-1", "title": "New conversation",
            "created_at": now, "updated_at": now}


def test_create_conversation_uses_authenticated_account(client, history_service):
    history_service.create_conversation.return_value = conversation()
    response = client.post("/conversations", json={"child_id": "child-1", "uid": "account-b"})
    assert response.status_code == 201
    history_service.create_conversation.assert_called_once_with("account-a", "child-1")


def test_create_conversation_requires_owned_child(client, history_service):
    history_service.create_conversation.return_value = None
    assert client.post("/conversations", json={"child_id": "child-1"}).status_code == 404


def test_list_conversations_passes_page_cursor(client, history_service):
    history_service.list_conversations.return_value = [conversation()]
    response = client.get("/conversations?child_id=child-1&limit=10&before=chat-2")
    assert response.status_code == 200
    history_service.list_conversations.assert_called_once_with("account-a", "child-1", 10, "chat-2")


def test_missing_child_does_not_read_history(client, history_service):
    history_service.get_child.return_value = None
    assert client.get("/conversations?child_id=missing").status_code == 404
    history_service.list_conversations.assert_not_called()


def test_missing_firestore_index_returns_setup_error(client, history_service):
    history_service.list_conversations.side_effect = FailedPrecondition("PRIVATE_PROJECT_INDEX_LINK")
    response = client.get("/conversations?child_id=child-1")
    assert response.status_code == 503
    assert "Firestore conversations index" in response.json()["detail"]
    assert "PRIVATE_PROJECT_INDEX_LINK" not in response.text


def test_get_conversation_returns_messages(client, history_service):
    history_service.get_conversation.return_value = {**conversation(), "messages": []}
    assert client.get("/conversations/chat-1").status_code == 200
    history_service.get_conversation.assert_called_once_with("account-a", "chat-1", 50, None)


def test_missing_conversation_returns_not_found(client, history_service):
    history_service.get_conversation.return_value = None
    assert client.get("/conversations/missing").status_code == 404


@pytest.mark.parametrize("limit", [0, 101])
def test_history_page_size_is_bounded(client, history_service, limit):
    assert client.get(f"/conversations/chat-1?limit={limit}").status_code == 422
    history_service.get_conversation.assert_not_called()


def test_invalid_cursor_returns_client_error(client, history_service):
    history_service.get_conversation.side_effect = ValueError("Invalid message cursor.")
    assert client.get("/conversations/chat-1?before=missing").status_code == 400


def test_delete_conversation_uses_authenticated_account(client, history_service):
    history_service.delete_conversation.return_value = True
    assert client.delete("/conversations/chat-1").status_code == 204
    history_service.delete_conversation.assert_called_once_with("account-a", "chat-1")


def test_delete_missing_conversation_returns_not_found(client, history_service):
    history_service.delete_conversation.return_value = False
    assert client.delete("/conversations/missing").status_code == 404


def test_delete_failure_returns_retry_message(client, history_service):
    history_service.delete_conversation.side_effect = RuntimeError("private database details")
    response = client.delete("/conversations/chat-1")
    assert response.status_code == 503
    assert "private database details" not in response.text


def test_storage_paths_are_scoped_to_account():
    database = MagicMock()
    service = CaregiverDataService(database)
    service._conversations("account-a")
    database.collection.assert_called_once_with("users")
    database.collection.return_value.document.assert_called_once_with("account-a")
    database.collection.return_value.document.return_value.collection.assert_called_once_with("conversations")


def test_delete_conversation_recursively_removes_nested_messages():
    database = MagicMock()
    service = CaregiverDataService(database)
    reference = service._conversations("account-a").document.return_value
    reference.get.return_value.exists = True
    assert service.delete_conversation("account-a", "chat-1")
    database.recursive_delete.assert_called_once_with(reference)


def test_history_reads_latest_page_in_display_order():
    service = CaregiverDataService(MagicMock())
    reference = service._conversations("account-a").document.return_value
    reference.get.return_value.id = "chat-1"
    reference.get.return_value.to_dict.return_value = conversation()
    query = reference.collection.return_value.order_by.return_value.limit.return_value
    newest, oldest = MagicMock(), MagicMock()
    newest.id, oldest.id = "message-2", "message-1"
    newest.to_dict.return_value = {"text": "Answer"}
    oldest.to_dict.return_value = {"text": "Question"}
    query.stream.return_value = [newest, oldest]
    result = service.get_conversation("account-a", "chat-1", limit=2)
    assert [message["id"] for message in result["messages"]] == ["message-1", "message-2"]
    reference.collection.return_value.order_by.return_value.limit.assert_called_once_with(2)


def test_message_cursor_must_exist_in_selected_conversation():
    service = CaregiverDataService(MagicMock())
    reference = service._conversations("account-a").document.return_value
    reference.get.return_value.to_dict.return_value = conversation()
    reference.collection.return_value.document.return_value.get.return_value.exists = False
    with pytest.raises(ValueError, match="Invalid message cursor"):
        service.get_conversation("account-a", "chat-1", before="other-message")


def test_child_deletion_removes_conversations_and_legacy_interactions():
    database = MagicMock()
    service = CaregiverDataService(database)
    child = MagicMock()
    legacy, chat = MagicMock(), MagicMock()
    # Use separate collection references, as a real Firestore client does.
    children, interactions, conversations = MagicMock(), MagicMock(), MagicMock()
    children.document.return_value = child
    interactions.where.return_value.stream.return_value = [legacy]
    conversations.where.return_value.stream.return_value = [chat]
    user = database.collection.return_value.document.return_value
    user.collection.side_effect = {"children": children, "interactions": interactions,
                                   "conversations": conversations}.__getitem__
    assert service.delete_child("account-a", "child-1")
    assert [call.args[0] for call in database.recursive_delete.call_args_list] == [
        legacy.reference, chat.reference, child,
    ]


def test_conversation_cursor_cannot_come_from_another_child():
    service = CaregiverDataService(MagicMock())
    cursor = service._conversations("account-a").document.return_value.get.return_value
    cursor.to_dict.return_value = {"child_id": "child-2"}
    with pytest.raises(ValueError, match="Invalid conversation cursor"):
        service.list_conversations("account-a", "child-1", before="chat-2")


def test_conversation_routes_require_authentication(client):
    assert client.get("/conversations?child_id=child-1").status_code == 401


def test_new_conversation_creation_has_no_readback_and_cannot_overwrite():
    from google.api_core.exceptions import AlreadyExists

    service = CaregiverDataService(MagicMock())
    service.get_child = MagicMock(return_value={"id": "child-1"})
    reference = service._conversations("account-a").document.return_value
    reference.id = "00000000-0000-4000-8000-000000000001"
    created = service.create_conversation("account-a", "child-1", conversation_id=reference.id)
    assert created["id"] == reference.id
    assert created["created_at"].utcoffset() is not None
    reference.create.assert_called_once()
    reference.get.assert_not_called()
    reference.create.side_effect = AlreadyExists("PRIVATE_DATABASE_DETAILS")
    with pytest.raises(AlreadyExists):
        service.create_conversation("account-a", "child-1", conversation_id=reference.id)
    reference.set.assert_not_called()


def test_new_conversation_still_requires_owned_child_before_writing():
    service = CaregiverDataService(MagicMock())
    service.get_child = MagicMock(return_value=None)
    assert service.create_conversation("account-a", "foreign-child", conversation_id="id") is None
    service.client.collection.assert_not_called()


@pytest.fixture
def coaching_dependencies(history_service):
    retrieval, coaching = MagicMock(), MagicMock()
    history_service.get_child.return_value = {
        "age_months": 6.0, "completed_months": 6, "age_days": 183, "in_scope": True,
    }
    history_service.get_conversation.return_value = {**conversation(), "messages": []}
    history_service.save_conversation_turn.return_value = "answer-1"
    history_service.create_interaction.return_value = "interaction-1"
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult("General information: Play together gently.", [],
                                                    answer_basis="general_information")
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    app.dependency_overrides[get_coaching_service] = lambda: coaching
    yield history_service, retrieval, coaching
    app.dependency_overrides.pop(get_retrieval_service, None)
    app.dependency_overrides.pop(get_coaching_service, None)


def test_preventive_feeding_question_reaches_generation_and_transactional_save(client, coaching_dependencies):
    data, _, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload(
        "My baby is 6 months old. Explain food preparation and choking precautions "
        "before introducing complementary foods. Do not assume readiness."
    ))
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    coaching.generate.assert_called_once()
    data.save_conversation_turn.assert_called_once()
    timings = response.headers["Server-Timing"]
    assert all(stage + ";dur=" in timings for stage in (
        "profile_lookup", "conversation_context", "retrieval",
        "generation", "response_safety", "interaction_save",
    ))


def test_active_choking_report_still_bypasses_generation_with_prevention_topic(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload(
        "Explain choking precautions, but my baby is choking on food right now."
    ))
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    coaching.generate.assert_not_called()
    retrieval.retrieve.assert_not_called()
    data.save_conversation_turn.assert_called_once()
    assert "generation;dur=" not in response.headers["Server-Timing"]


def test_profile_and_owned_history_reads_overlap_before_generation(client, coaching_dependencies):
    data, _, coaching = coaching_dependencies
    both_reading = Barrier(2)
    child, history = data.get_child.return_value, data.get_conversation.return_value

    def read_child(*args, **kwargs):
        both_reading.wait(timeout=3)
        return child

    def read_history(*args, **kwargs):
        both_reading.wait(timeout=3)
        return history

    data.get_child.side_effect = read_child
    data.get_conversation.side_effect = read_history
    response = client.post("/coach", json=coaching_payload("How can we play with stacking cups?"))
    assert response.status_code == 200
    data.get_child.assert_called_once_with("account-a", "child-1")
    data.get_conversation.assert_called_once_with("account-a", "chat-1", 8, expected_child_id="child-1")
    coaching.generate.assert_called_once()


def test_cached_sources_still_reload_profile_and_generate_each_answer(client, coaching_dependencies, monkeypatch):
    data, _, coaching = coaching_dependencies
    source_client = MagicMock()
    source_client.query_points.return_value.points = [MagicMock(id="p1", score=0.9, payload={
        "passage_id": "p1", "text": "Talk together gently.", "title": "Sharing a book",
        "source_title": "Care reference", "source_url": "https://example.test/book", "pdf_page": 2,
        "source_age": {"min_months": 0, "max_months_exclusive": 25}, "routines": ["reading"],
    })]
    retrieval = RetrievalService(client=source_client, cache_ttl_seconds=60)
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    monkeypatch.setattr("backend.api.v1.endpoints.coaching.select_care_references", lambda *args: [])
    coaching.generate.side_effect = lambda question, age, routine, passages, **kwargs: CoachingResult(
        "Talk together gently." if coaching.generate.call_count == 1 else "Point at a picture together.", passages,
    )
    question = coaching_payload("How can we enjoy a cloth picture book?")
    try:
        first = client.post("/coach", json=question)
        data.get_child.return_value["milestones"] = ["A new saved observation"]
        second = client.post("/coach", json=question)
        assert first.status_code == second.status_code == 200
        assert first.json()["answer"] != second.json()["answer"]
        assert second.json()["citations"] == first.json()["citations"]
        assert second.json()["citations"][0]["source_url"] == "https://example.test/book"
        assert data.get_child.call_count == data.get_conversation.call_count == coaching.generate.call_count == 2
        assert coaching.generate.call_args.kwargs["profile_context"] == {"milestones": ["A new saved observation"]}
        assert "A new saved observation" not in repr(retrieval._cache)
        source_client.query_points.assert_called_once()
    finally:
        retrieval.close()


def test_missing_profile_takes_priority_over_parallel_history_failure(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_child.return_value = None
    data.get_conversation.side_effect = RuntimeError("PRIVATE_HISTORY_DETAILS")
    response = client.post("/coach", json=coaching_payload("How can we play with stacking cups?"))
    assert response.status_code == 404
    assert "PRIVATE_HISTORY_DETAILS" not in response.text
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("question", ["My baby has a fever.", "My baby's skin looks yellow."])
def test_age_specific_urgent_messages_skip_parallel_history(client, coaching_dependencies, question):
    data, retrieval, coaching = coaching_dependencies
    data.get_child.return_value.update(age_months=0, completed_months=0, age_days=0)
    data.get_conversation.side_effect = RuntimeError("History must not be read")
    response = client.post("/coach", json=coaching_payload(question))
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    data.get_conversation.assert_not_called()
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_cautious_prefetch_screen_does_not_change_actual_profile_age(client, coaching_dependencies):
    data, _, coaching = coaching_dependencies
    child = data.get_child.return_value
    profile_read = []

    def read_child(*args):
        profile_read.append(True)
        return child

    def read_history(*args, **kwargs):
        assert profile_read
        return {**conversation(), "messages": []}

    data.get_child.side_effect = read_child
    data.get_conversation.side_effect = read_history
    response = client.post("/coach", json=coaching_payload("My baby has a fever."))
    assert response.status_code == 200
    assert response.json()["child_age_months"] == 6
    assert response.json()["status"] != "escalated"
    data.get_conversation.assert_called_once()
    coaching.generate.assert_called_once()


@pytest.mark.asyncio
async def test_cancelling_parallel_reads_cleans_up_both_tasks(monkeypatch):
    import asyncio
    from backend.api.v1.endpoints import coaching as endpoint
    from backend.schemas.coaching import CoachingRequest

    started = {"get_child": asyncio.Event(), "get_conversation": asyncio.Event()}
    finished = set()

    async def blocked_read(method, *args, **kwargs):
        name = method.__name__
        started[name].set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.add(name)

    monkeypatch.setattr(endpoint, "run_in_threadpool", blocked_read)
    service = CaregiverDataService(MagicMock())
    task = asyncio.create_task(endpoint.read_coaching_data(
        service, "account-a", CoachingRequest(**coaching_payload()), "test-request", parallel=True,
    ))
    for event in started.values():
        await asyncio.wait_for(event.wait(), timeout=3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished == set(started)


def test_first_message_starts_and_answers_in_one_request_without_reading_empty_history(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    cid = "00000000-0000-4000-8000-000000000001"
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": cid,
                                            "start_conversation": True, "question": "Dressing ideas?"})
    assert response.status_code == 200
    assert response.json()["conversation_id"] == cid
    data.create_conversation.assert_called_once_with("account-a", "child-1", conversation_id=cid)
    data.get_conversation.assert_not_called()
    coaching.generate.assert_called_once()
    data.save_conversation_turn.assert_called_once()
    data.create_interaction.assert_not_called()


def test_first_message_collision_cannot_overwrite_or_generate(client, coaching_dependencies):
    from google.api_core.exceptions import AlreadyExists

    data, retrieval, coaching = coaching_dependencies
    data.create_conversation.side_effect = AlreadyExists("PRIVATE_DATABASE_DETAILS")
    response = client.post("/coach", json={"child_id": "child-1",
        "conversation_id": "00000000-0000-4000-8000-000000000001",
        "start_conversation": True, "question": "Dressing ideas?"})
    assert response.status_code == 409
    assert "PRIVATE_DATABASE_DETAILS" not in response.text
    coaching.generate.assert_not_called()
    data.save_conversation_turn.assert_not_called()


def test_urgent_first_message_survives_conversation_creation_failure(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.create_conversation.side_effect = RuntimeError("PRIVATE_DATABASE_DETAILS")
    response = client.post("/coach", json={"child_id": "child-1",
        "conversation_id": "00000000-0000-4000-8000-000000000001", "start_conversation": True,
        "question": "My baby cannot breathe", "support_country": "KE"})
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert response.json()["message_id"] is None
    assert response.json()["support_resources"]
    assert "PRIVATE_DATABASE_DETAILS" not in response.text
    coaching.generate.assert_not_called()
    retrieval.retrieve.assert_not_called()


@pytest.mark.parametrize("cid", [None, "existing-firestore-id", "00000000-0000-1000-8000-000000000001"])
def test_start_requires_a_new_canonical_uuid(client, coaching_dependencies, cid):
    data, _, coaching = coaching_dependencies
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": cid,
                                            "start_conversation": True, "question": "Dressing ideas?"})
    assert response.status_code == 422
    data.create_conversation.assert_not_called()
    coaching.generate.assert_not_called()


def coaching_payload(question="Play ideas"):
    return {"child_id": "child-1", "conversation_id": "chat-1", "question": question}


def test_coaching_uses_current_owned_milestones_and_ignores_browser_profile_context(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_child.return_value["milestones"] = ["Current server observation"]
    response = client.post("/coach", json={**coaching_payload(), "profile_context": {"milestones": ["UNTRUSTED_BROWSER_DATA"]}})
    assert response.status_code == 200
    data.get_child.assert_called_once_with("account-a", "child-1")
    assert coaching.generate.call_args.kwargs["profile_context"] == {"milestones": ["Current server observation"]}
    assert "Current server observation" not in str(retrieval.retrieve.call_args)
    assert "profile_context" not in data.save_conversation_turn.call_args.args[5]


def test_explicit_different_child_age_does_not_inherit_selected_profile_notes(client, coaching_dependencies):
    data, _, coaching = coaching_dependencies
    data.get_child.return_value["milestones"] = ["PRIVATE_PROFILE_OBSERVATION"]
    response = client.post("/coach", json=coaching_payload("Play ideas for my 18-month-old?"))
    assert response.status_code == 200
    assert "profile_context" not in coaching.generate.call_args.kwargs


@pytest.mark.parametrize("paid,testing", [(True, False), (False, True)])
def test_health_context_is_not_sent_to_retrieval_or_duplicated_in_history_metadata(client, coaching_dependencies, monkeypatch, paid, testing):
    from backend.core.config import settings
    data, retrieval, coaching = coaching_dependencies
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", paid)
    monkeypatch.setattr(settings, "GEMINI_NONPERSONAL_TESTING_CONFIRMED", testing)
    data.get_child.return_value.update(use_health_details=True, health_details={"allergies": "PRIVATE_NOTE"})
    response = client.post("/coach", json=coaching_payload())
    assert response.status_code == 200
    assert coaching.generate.call_args.kwargs["profile_context"]["health_details"] == {"allergies": "PRIVATE_NOTE"}
    assert "PRIVATE_NOTE" not in str(retrieval.retrieve.call_args)
    stored = data.save_conversation_turn.call_args.args[5]
    assert stored["health_context_used"] is True
    assert "PRIVATE_NOTE" not in str(stored)


def test_provider_withdrawal_stops_health_context_from_reentering_via_history(client, coaching_dependencies, monkeypatch):
    from backend.core.config import settings
    data, _, coaching = coaching_dependencies
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", False)
    monkeypatch.setattr(settings, "GEMINI_NONPERSONAL_TESTING_CONFIRMED", False)
    data.get_conversation.return_value = {**conversation(), "messages": [
        {"role": "user", "text": "PRIVATE_HISTORY"},
        {"role": "assistant", "text": "PRIVATE_REPLY", "status": "answered", "health_context_used": True},
    ]}
    assert client.post("/coach", json=coaching_payload()).status_code == 200
    assert "conversation_context" not in coaching.generate.call_args.kwargs


@pytest.mark.parametrize("choice,current_revision,reused", [(False, "a" * 32, False), (True, "b" * 32, False), (True, "a" * 32, True)])
def test_health_history_requires_current_notes_and_sharing_choice(client, coaching_dependencies, monkeypatch, choice, current_revision, reused):
    from backend.core.config import settings
    data, _, coaching = coaching_dependencies
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", True)
    data.get_child.return_value.update(use_health_details=choice, health_context_revision=current_revision)
    data.get_conversation.return_value = {**conversation(), "messages": [
        {"role": "user", "text": "Play ideas?"},
        {"role": "assistant", "text": "An earlier suggestion.", "status": "answered",
         "health_context_used": True, "health_context_revision": "a" * 32},
    ]}
    assert client.post("/coach", json=coaching_payload()).status_code == 200
    assert ("conversation_context" in coaching.generate.call_args.kwargs) is reused


def test_coaching_saves_conversation_instead_of_duplicate_interaction(client, coaching_dependencies):
    data, _, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "chat-1"
    assert body["message_id"] == "answer-1"
    assert body["interaction_id"] is None
    data.create_interaction.assert_not_called()
    coaching.generate.assert_called_once()
    args = data.save_conversation_turn.call_args.args
    assert args[:5] == ("account-a", "chat-1", "child-1", "Play ideas", None)
    assert args[5]["text"] == body["answer"]
    assert args[5]["status"] == "answered"
    assert args[5]["answer_basis"] == "general_information"
    assert args[5]["reference_status"] == "no_match"


def test_coaching_without_conversation_preserves_existing_storage(client, coaching_dependencies):
    data, _, _ = coaching_dependencies
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 200
    assert response.json()["interaction_id"] == "interaction-1"
    data.create_interaction.assert_called_once()
    data.save_conversation_turn.assert_not_called()
    data.get_conversation.assert_not_called()


def test_wrong_conversation_is_rejected_before_model_calls(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_conversation.return_value = None
    assert client.post("/coach", json=coaching_payload()).status_code == 404
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.save_conversation_turn.assert_not_called()


def test_follow_up_uses_server_history_for_retrieval_and_generation(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    history = [{"role": "user", "text": "How can I talk during feeding?"},
               {"role": "assistant", "text": "Talk softly.", "status": "answered"}]
    data.get_conversation.return_value = {**conversation(), "messages": history}
    reference = RetrievedPassage("p1", "Talk with your baby.", "Talk", "Reference", 1,
                                 "https://example.test/reference", 1.0, "6-8 months", ["feeding"])
    retrieval.retrieve.return_value = [reference]
    coaching.generate.return_value = CoachingResult("Talk with your baby.", [reference])
    response = client.post("/coach", json={**coaching_payload("What else can I try?"),
        "conversation_context": [{"role": "assistant", "text": "BROWSER_SUPPLIED_HISTORY"}]})
    assert response.status_code == 200
    data.get_conversation.assert_called_once_with("account-a", "chat-1", 8, expected_child_id="child-1")
    assert "How can I talk during feeding?" in retrieval.retrieve.call_args.args[0]
    assert retrieval.retrieve.call_args.args[1] == 6
    assert retrieval.retrieve.call_args.kwargs["child_age_days"] == 183
    assert coaching.generate.call_args.args[0] == "What else can I try?"
    assert coaching.generate.call_args.kwargs["conversation_context"] == [
        {"role": "user", "text": history[0]["text"]}, {"role": "assistant", "text": history[1]["text"]},
    ]
    assert data.save_conversation_turn.call_args.args[3] == "What else can I try?"


def test_follow_up_retains_original_request_four_exchanges_back(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    topic = "How can I share a cloth picture book with my baby?"
    history = []
    for question in [topic, "More ideas", "Tell me more", "Anything else I can do?"]:
        history.extend([{"role": "user", "text": question},
                        {"role": "assistant", "text": "Talk together gently.", "status": "answered"}])
    data.get_conversation.return_value = {**conversation(), "messages": history}
    response = client.post("/coach", json=coaching_payload("What else can I try?"))
    assert response.status_code == 200
    data.get_conversation.assert_called_once_with("account-a", "chat-1", 8, expected_child_id="child-1")
    assert topic in retrieval.retrieve.call_args.args[0]
    assert len(coaching.generate.call_args.kwargs["conversation_context"]) == 8
    assert coaching.generate.call_args.kwargs["conversation_context"][0]["text"] == topic


def test_follow_up_preserves_explicit_subject_age_instead_of_different_profile_age(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_conversation.return_value = {**conversation(), "messages": [
        {"role": "user", "text": "How can I play with my 3-year-old?"},
        {"role": "assistant", "text": "Try simple pretend play.", "status": "answered"},
    ]}
    response = client.post("/coach", json=coaching_payload("What else can I try?"))
    assert response.status_code == 200
    assert response.json()["child_age_months"] == 36
    assert response.json()["response_kind"] == "age_out_of_scope"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    assert data.save_conversation_turn.call_args.args[5]["child_age_months"] == 36


def test_named_clarification_retrieves_definitions_using_permitted_caregiver_context(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_child.return_value.update(age_months=0.5, completed_months=0, age_days=14)
    history = [
        {"role": "user", "text": "I am bathing my baby."},
        {"role": "assistant", "text": "Are you doing a full bath or top and tailing?", "status": "answered"},
    ]
    data.get_conversation.return_value = {**conversation(), "messages": history}
    reference = RetrievedPassage("definition", "Top and tailing means washing selected areas outside a bath.",
                                 "Top and tailing", "NHS", None, "https://www.nhs.uk/baby/bathing",
                                 0.75, "0 to under 12 months", ["bathing"])
    retrieval.retrieve.return_value = [reference]
    coaching.generate.return_value = CoachingResult(reference.text, [reference])
    question = "what is full bath, top and tailing?"
    response = client.post("/coach", json=coaching_payload(question))
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["answer"] == reference.text
    assert response.json()["citations"][0]["passage_id"] == "definition"
    assert retrieval.retrieve.call_args.args[0] == "I am bathing my baby.\nFollow-up: " + question
    assert retrieval.retrieve.call_args.kwargs["child_age_days"] == 14
    assert coaching.generate.call_args.args[0] == question
    data.save_conversation_turn.assert_called_once()


def test_unresolved_follow_up_does_not_generate_arbitrary_guidance(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload("What else can I try?"))
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.save_conversation_turn.assert_called_once()


def test_context_failure_is_not_silently_treated_as_an_empty_chat(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_conversation.side_effect = RuntimeError("PRIVATE_DATABASE_DETAILS")
    response = client.post("/coach", json=coaching_payload("What else can I try?"))
    assert response.status_code == 503
    assert "PRIVATE_DATABASE_DETAILS" not in response.text
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_context_read_rejects_another_child_before_loading_messages():
    service = CaregiverDataService(MagicMock())
    reference = service._conversations("account-a").document.return_value
    reference.get.return_value.to_dict.return_value = {"child_id": "child-2"}
    assert service.get_conversation("account-a", "chat-1", 6, expected_child_id="child-1") is None
    reference.collection.assert_not_called()


@pytest.mark.parametrize("question,status", [
    ("My baby cannot breathe.", "escalated"),
    ("I feel depressed since giving birth.", "caregiver_support"),
])
def test_safety_messages_use_conversation_storage(client, coaching_dependencies, question, status):
    data, retrieval, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload(question))
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert data.save_conversation_turn.call_args.args[-1]["status"] == status
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.get_conversation.assert_not_called()


def test_safety_referral_survives_conversation_storage_failure(client, coaching_dependencies):
    data, _, _ = coaching_dependencies
    data.save_conversation_turn.side_effect = RuntimeError("database unavailable")
    response = client.post("/coach", json=coaching_payload("My baby cannot breathe."))
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert response.json()["message_id"] is None


def test_urgent_turn_does_not_depend_on_previous_chat_or_history_availability(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.get_conversation.side_effect = RuntimeError("History unavailable")
    response = client.post("/coach", json=coaching_payload("My baby cannot keep his milk down."))
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert "urgent medical care now" in response.json()["answer"]
    data.get_conversation.assert_not_called()
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_explicit_diagnosis_request_is_saved_as_referral_not_generated(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload("Can you diagnose why my child is not talking?"))
    assert response.status_code == 200
    assert response.json()["response_kind"] == "professional_referral"
    assert data.save_conversation_turn.call_args.args[-1]["response_kind"] == "professional_referral"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("answer,status", [
    ("Talk with your baby.", "answered"),
    ("Give 5 mg of medicine.", "safety_blocked"),
])
def test_conversation_storage_receives_only_checked_answer(client, coaching_dependencies, answer, status):
    data, retrieval, coaching = coaching_dependencies
    reference = RetrievedPassage("p1", "Talk with your baby.", "Talk", "Reference", 1,
                                 "https://example.test/reference", 1.0, "6-8 months", ["play"])
    retrieval.retrieve.return_value = [reference]
    coaching.generate.return_value = CoachingResult(answer, [reference])
    response = client.post("/coach", json=coaching_payload())
    assert response.status_code == 200
    assert response.json()["status"] == status
    saved = data.save_conversation_turn.call_args.args[-1]
    assert saved["text"] == (SAFE_RESPONSE if status == "safety_blocked" else answer)
    assert saved["citations"] == response.json()["citations"]


def test_conversation_deleted_during_generation_is_not_recreated(client, coaching_dependencies):
    data, _, _ = coaching_dependencies
    data.save_conversation_turn.side_effect = ValueError("Conversation not found")
    assert client.post("/coach", json=coaching_payload()).status_code == 404
    data.create_interaction.assert_not_called()


def test_conversation_storage_failure_returns_clear_error(client, coaching_dependencies):
    data, _, _ = coaching_dependencies
    data.save_conversation_turn.side_effect = RuntimeError("PRIVATE_DATABASE_DETAILS")
    response = client.post("/coach", json=coaching_payload())
    assert response.status_code == 503
    assert "PRIVATE_DATABASE_DETAILS" not in response.text


def test_feedback_targets_assistant_message(client, history_service):
    history_service.save_message_feedback.return_value = datetime.now(timezone.utc)
    response = client.post("/coach/answer-1/feedback", json={
        "conversation_id": "chat-1", "helpful": True, "comment": "Clear guidance",
    })
    assert response.status_code == 200
    assert response.json()["message_id"] == "answer-1"
    assert response.json()["interaction_id"] is None
    history_service.save_message_feedback.assert_called_once_with(
        "account-a", "chat-1", "answer-1", True, "Clear guidance",
    )
    history_service.save_feedback.assert_not_called()


def test_feedback_without_conversation_keeps_legacy_path(client, history_service):
    history_service.save_feedback.return_value = datetime.now(timezone.utc)
    assert client.post("/coach/interaction-1/feedback", json={"helpful": False}).status_code == 200
    history_service.save_feedback.assert_called_once_with("account-a", "interaction-1", False, None)
    history_service.save_message_feedback.assert_not_called()


def test_numeric_feedback_uses_owned_message_path(client, history_service):
    history_service.save_message_feedback.return_value = datetime.now(timezone.utc)
    response = client.post("/coach/answer-1/feedback", json={
        "conversation_id": "chat-1", "rating": 4, "reasons": ["unclear"],
    })
    assert response.status_code == 200
    assert response.json()["rating"] == 4
    assert response.json()["helpful"] is None
    history_service.save_message_feedback.assert_called_once_with(
        "account-a", "chat-1", "answer-1", None, None, rating=4, reasons=["unclear"],
    )
    history_service.save_feedback.assert_not_called()


def test_numeric_feedback_for_missing_message_is_not_saved(client, history_service):
    history_service.save_message_feedback.return_value = None
    assert client.post("/coach/missing/feedback", json={
        "conversation_id": "chat-1", "rating": 5,
    }).status_code == 404


def test_missing_assistant_message_rejects_feedback(client, history_service):
    history_service.save_message_feedback.return_value = None
    assert client.post("/coach/missing/feedback", json={
        "conversation_id": "chat-1", "helpful": True,
    }).status_code == 404


@pytest.fixture
def transactional_storage(monkeypatch):
    # Execute the transaction callback without connecting to Firestore.
    monkeypatch.setattr("backend.services.caregiver_data.firestore.transactional", lambda function: function)
    database = MagicMock()
    service = CaregiverDataService(database)
    children, conversations = MagicMock(), MagicMock()
    children.document.return_value.get.return_value.to_dict.return_value = {}
    account = database.collection.return_value.document.return_value
    account.collection.side_effect = {"children": children, "conversations": conversations}.__getitem__
    reference = conversations.document.return_value
    reference.get.return_value.to_dict.return_value = {"child_id": "child-1", "message_count": 0}
    reference.path = "users/account-a/conversations/chat-1"
    children.document.return_value.path = "users/account-a/children/child-1"
    reference.collection.return_value.document.return_value.path = "users/account-a/conversations/chat-1/messages/answer-1"

    def batch_get(references, **kwargs):
        for document in reversed(references):
            snapshot = document.get.return_value
            snapshot.reference = document
            yield snapshot
    database.get_all.side_effect = batch_get
    return service, database.transaction.return_value, reference, children


def test_turn_saves_two_ordered_messages_in_one_transaction(transactional_storage):
    service, transaction, reference, _ = transactional_storage
    question, answer = MagicMock(), MagicMock()
    answer.id = "answer-1"
    reference.collection.return_value.document.side_effect = [question, answer]
    saved_id = service.save_conversation_turn(
        "account-a", "chat-1", "child-1", "  Play\nideas  ", "play",
        {"text": "Talk softly.", "status": "answered"},
    )
    assert saved_id == "answer-1"
    writes = transaction.set.call_args_list
    assert len(writes) == 2
    assert writes[0].args[0] is question
    assert writes[0].args[1]["role"] == "user"
    assert writes[0].args[1]["sequence"] == 0
    assert writes[1].args[0] is answer
    assert writes[1].args[1]["role"] == "assistant"
    assert writes[1].args[1]["sequence"] == 1
    update = transaction.update.call_args.args[1]
    assert update["message_count"] == 2
    assert update["title"] == "Play ideas"
    service.client.get_all.assert_called_once_with(
        [reference, service._children("account-a").document("child-1")],
        field_paths=("child_id", "message_count", "deleting"), transaction=transaction,
    )
    reference.get.assert_not_called()
    service._children("account-a").document("child-1").get.assert_not_called()


def test_follow_up_turn_preserves_title_and_increments_sequence(transactional_storage):
    service, transaction, reference, _ = transactional_storage
    reference.get.return_value.to_dict.return_value = {"child_id": "child-1", "message_count": 2}
    service.save_conversation_turn("account-a", "chat-1", "child-1", "More ideas?", None,
                                   {"text": "Sing softly."})
    assert transaction.set.call_args_list[0].args[1]["sequence"] == 2
    assert transaction.set.call_args_list[1].args[1]["sequence"] == 3
    assert "title" not in transaction.update.call_args.args[1]


@pytest.mark.parametrize("missing", ["conversation", "child", "wrong_child", "deleting_conversation", "deleting_child"])
def test_turn_rechecks_parent_ownership_before_writing(transactional_storage, missing):
    service, transaction, reference, children = transactional_storage
    if missing == "conversation":
        reference.get.return_value.exists = False
    elif missing == "child":
        children.document.return_value.get.return_value.exists = False
    elif missing == "wrong_child":
        reference.get.return_value.to_dict.return_value = {"child_id": "child-2"}
    elif missing == "deleting_conversation":
        reference.get.return_value.to_dict.return_value = {"child_id": "child-1", "deleting": True}
    else:
        children.document.return_value.get.return_value.to_dict.return_value = {"deleting": True}
    with pytest.raises(ValueError, match="Conversation not found"):
        service.save_conversation_turn("account-a", "chat-1", "child-1", "Play ideas", None,
                                       {"text": "Talk softly."})
    transaction.set.assert_not_called()
    transaction.update.assert_not_called()


@pytest.mark.parametrize("role", ["assistant", "user"])
def test_storage_feedback_only_updates_assistant_messages(transactional_storage, role):
    service, transaction, reference, _ = transactional_storage
    message = reference.collection.return_value.document.return_value
    message.get.return_value.to_dict.return_value = {"role": role}
    recorded_at = service.save_message_feedback("account-a", "chat-1", "answer-1", True, " Clear ")
    service.client.get_all.assert_called_once_with(
        [reference, message], field_paths=("role", "deleting"), transaction=transaction,
    )
    reference.get.assert_not_called()
    message.get.assert_not_called()
    if role == "assistant":
        assert recorded_at is not None
        feedback = transaction.update.call_args.args[1]["feedback"]
        assert feedback["comment"] == "Clear"
        assert feedback["helpful"] is True
    else:
        assert recorded_at is None
        transaction.update.assert_not_called()


def test_numeric_feedback_edit_replaces_previous_values_without_private_review_state(transactional_storage):
    service, transaction, reference, _ = transactional_storage
    message = reference.collection.return_value.document.return_value
    message.get.return_value.to_dict.return_value = {
        "role": "assistant", "feedback": {"rating": 1, "reasons": ["unclear"], "review_status": "resolved"},
    }
    saved = service.save_message_feedback("account-a", "chat-1", "answer-1", None, None,
                                         rating=5, reasons=[])
    feedback = transaction.update.call_args.args[1]["feedback"]
    assert feedback["rating"] == 5
    assert feedback["reasons"] == []
    assert feedback["comment"] is None
    assert feedback["recorded_at"] == saved
    assert "review_status" not in feedback


@pytest.mark.parametrize("failure", ["missing_reply", "duplicate_reply", "foreign_reply", "transport_error"])
def test_invalid_transaction_batch_never_writes_partial_turns(transactional_storage, failure):
    from types import SimpleNamespace

    service, transaction, reference, children = transactional_storage
    def broken(references, **kwargs):
        snapshot = reference.get.return_value
        snapshot.reference = reference
        yield snapshot
        if failure == "duplicate_reply":
            yield snapshot
        elif failure == "foreign_reply":
            yield SimpleNamespace(reference=SimpleNamespace(path="users/another-account/children/child-1"))
        elif failure == "transport_error":
            raise RuntimeError("Batch read failed.")
    service.client.get_all.side_effect = broken
    with pytest.raises(RuntimeError):
        service.save_conversation_turn("account-a", "chat-1", "child-1", "Play ideas", None,
                                       {"text": "Talk softly."})
    transaction.set.assert_not_called()
    transaction.update.assert_not_called()
