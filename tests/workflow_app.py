"""Loopback-only API fixture for frontend integration; external services are fake."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace
from threading import Event
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anyio
import uvicorn
from fastapi import Request

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service, get_speech_service
from backend.core.privacy import CONSENT_VERSION
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.coaching import CoachingResult
from backend.services.retrieval import RetrievedPassage


class MemoryData:
    def __init__(self):
        self.chats = {}

    def get_consent(self, uid):
        return {"consent_version": CONSENT_VERSION, "consent_at": datetime.now(timezone.utc), "caregiver_authority": True}

    def list_children(self, uid):
        first = {"id": "workflow-child", "name": "Workflow child", "date_of_birth": "2026-04-30",
                 "age_months": 6, "age_days": 183, "completed_months": 6, "in_scope": True,
                 "age_label": "6 months", "baseline_milestones": [], "milestones": []}
        return [first, {**first, "id": "other-child", "name": "Other child", "date_of_birth": "2025-04-30",
                        "age_months": 18, "completed_months": 18, "age_days": 548, "age_label": "18 months"}]

    def get_child(self, uid, child_id):
        return next((c for c in self.list_children(uid) if c["id"] == child_id), None)

    def get_coaching_documents(self, uid, child_id, conversation_id):
        child = self.get_child(uid, child_id)
        return {"consent": self.get_consent(uid),
                "child_snapshot": SimpleNamespace(exists=child is not None, profile=child, to_dict=lambda: child or {}),
                "conversation_snapshot": self.chats.get(conversation_id)}

    @staticmethod
    def _child_response(snapshot):
        return snapshot.profile

    def list_conversations(self, uid, child_id, limit=30, before=None):
        return [{k: v for k, v in c.items() if k != "messages"} for c in self.chats.values() if c["child_id"] == child_id]

    def create_conversation(self, uid, child_id, *, conversation_id=None):
        if not self.get_child(uid, child_id):
            return None
        cid = conversation_id or f"chat-{len(self.chats) + 1}"
        if cid in self.chats:
            from google.api_core.exceptions import AlreadyExists
            raise AlreadyExists("Conversation already exists")
        now = datetime.now(timezone.utc)
        self.chats[cid] = {"id": cid, "child_id": child_id, "title": "New conversation",
                           "created_at": now, "updated_at": now, "messages": []}
        return self.chats[cid]

    def get_conversation(self, uid, conversation_id, limit=50, before=None, *, expected_child_id=None,
                         prefetched_snapshot=None):
        c = self.chats.get(conversation_id)
        if not c or expected_child_id and c["child_id"] != expected_child_id:
            return None
        return c

    def save_conversation_turn(self, uid, conversation_id, child_id, question, routine, response):
        c = self.get_conversation(uid, conversation_id, expected_child_id=child_id)
        if not c:
            raise ValueError("Conversation unavailable.")
        now = datetime.now(timezone.utc)
        count = len(c["messages"])
        c["messages"].extend([
            {"id": f"q{count}", "role": "user", "text": question, "created_at": now},
            {"id": f"a{count}", "role": "assistant", "created_at": now, **response},
        ])
        c.update(title=question[:80] if count == 0 else c["title"], updated_at=now)
        return f"a{count}"

    def save_message_feedback(self, uid, conversation_id, message_id, helpful, comment, **values):
        c = self.chats.get(conversation_id)
        if c:
            message = next((m for m in c["messages"] if m["id"] == message_id), None)
            if message:
                now = datetime.now(timezone.utc)
                message["feedback"] = {"helpful": helpful, "comment": comment, **values, "recorded_at": now}
                return now
        return None

    def delete_conversation(self, uid, conversation_id):
        return self.chats.pop(conversation_id, None) is not None


reference = RetrievedPassage("workflow-reference", "Talk gently while dressing.", "Dressing together",
                             "Workflow reference", None, "https://www.unicef.org/parenting/", 0.9, "0-24 months", [])
stream_gate = Event()


def generate(question, age, routine, evidence, **kwargs):
    if "babbling" in question.lower() and kwargs.get("on_delta"):
        kwargs["on_delta"]("Talk gently. ")
        if not stream_gate.wait(10):
            raise RuntimeError("Fixture stream not released")
        kwargs["on_delta"]("Pause and listen.")
        return CoachingResult("Talk gently. Pause and listen.", [reference])
    if "outage" in question.lower():
        raise RuntimeError("Fixture generation outage")
    if "slow" in question.lower():
        time.sleep(0.5)
    return CoachingResult("Talk gently while dressing.", [reference])


def transcribe(audio, **kwargs):
    with wave.open(BytesIO(audio)) as recording:
        assert recording.getnchannels() == 1 and recording.getframerate() == 16000
        duration = recording.getnframes() / recording.getframerate()
    assert kwargs["language"] == "en"
    return {"text": "I am dressing my baby.", "audio_seconds": duration, "processing_seconds": 0.01}


if __name__ == "__main__":
    data = MemoryData()
    def identity(request: Request):
        request.state.account_role = "caregiver"
        return {"uid": "workflow-account"}

    app.dependency_overrides.update({
        require_authenticated_user: identity,
        get_caregiver_data_service: lambda: data,
        get_coaching_service: lambda: SimpleNamespace(generate=generate),
        get_retrieval_service: lambda: SimpleNamespace(retrieve=lambda *a, **kw: [reference]),
        get_speech_service: lambda: SimpleNamespace(transcribe=transcribe),
    })
    app.state.speech_limiter = anyio.CapacityLimiter(1)
    from backend.core.request_admission import RequestAdmission
    app.state.request_admission = RequestAdmission(enforce_rate=False)

    @app.get("/__workflow/ready")
    def ready():
        return {"ready": True}

    @app.post("/__workflow/reset")
    def reset():
        data.chats.clear()
        stream_gate.clear()
        return {"reset": True}

    @app.post("/__workflow/continue")
    def continue_stream():
        stream_gate.set()
        return {"continued": True}

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    print(f"WORKFLOW_PORT={listener.getsockname()[1]}", flush=True)
    uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="critical", access_log=False)).run(sockets=[listener])
