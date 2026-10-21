"""Conversation routes use authenticated ownership and bounded history reads."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.api.dependencies import get_caregiver_data_service
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.caregiver_data import CaregiverDataService


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
