"""Conversation routes use authenticated ownership and bounded history reads."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from google.api_core.exceptions import FailedPrecondition

import pytest

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingResult
from backend.services.retrieval import RetrievedPassage
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


@pytest.fixture
def coaching_dependencies(history_service):
    retrieval, coaching = MagicMock(), MagicMock()
    history_service.get_child.return_value = {
        "age_months": 6.0, "completed_months": 6, "age_days": 183, "in_scope": True,
    }
    history_service.conversation_belongs_to_child.return_value = True
    history_service.save_conversation_turn.return_value = "answer-1"
    history_service.create_interaction.return_value = "interaction-1"
    retrieval.retrieve.return_value = []
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    app.dependency_overrides[get_coaching_service] = lambda: coaching
    yield history_service, retrieval, coaching
    app.dependency_overrides.pop(get_retrieval_service, None)
    app.dependency_overrides.pop(get_coaching_service, None)


def coaching_payload(question="Play ideas"):
    return {"child_id": "child-1", "conversation_id": "chat-1", "question": question}


def test_coaching_saves_conversation_instead_of_duplicate_interaction(client, coaching_dependencies):
    data, _, coaching = coaching_dependencies
    response = client.post("/coach", json=coaching_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "chat-1"
    assert body["message_id"] == "answer-1"
    assert body["interaction_id"] is None
    data.create_interaction.assert_not_called()
    coaching.generate.assert_not_called()
    args = data.save_conversation_turn.call_args.args
    assert args[:5] == ("account-a", "chat-1", "child-1", "Play ideas", None)
    assert args[5]["text"] == body["answer"]
    assert args[5]["status"] == "no_evidence"


def test_coaching_without_conversation_preserves_existing_storage(client, coaching_dependencies):
    data, _, _ = coaching_dependencies
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 200
    assert response.json()["interaction_id"] == "interaction-1"
    data.create_interaction.assert_called_once()
    data.save_conversation_turn.assert_not_called()
    data.conversation_belongs_to_child.assert_not_called()


def test_wrong_conversation_is_rejected_before_model_calls(client, coaching_dependencies):
    data, retrieval, coaching = coaching_dependencies
    data.conversation_belongs_to_child.return_value = False
    assert client.post("/coach", json=coaching_payload()).status_code == 404
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.save_conversation_turn.assert_not_called()


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


def test_safety_referral_survives_conversation_storage_failure(client, coaching_dependencies):
    data, _, _ = coaching_dependencies
    data.save_conversation_turn.side_effect = RuntimeError("database unavailable")
    response = client.post("/coach", json=coaching_payload("My baby cannot breathe."))
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert response.json()["message_id"] is None


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
    if role == "assistant":
        assert recorded_at is not None
        feedback = transaction.update.call_args.args[1]["feedback"]
        assert feedback["comment"] == "Clear"
        assert feedback["helpful"] is True
    else:
        assert recorded_at is None
        transaction.update.assert_not_called()
