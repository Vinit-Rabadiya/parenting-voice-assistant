"""Provider streaming, checked prefixes, final persistence and disconnect boundaries."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import Request
import httpx
import pytest

from backend.api.coaching_stream import CoachingStream, StreamCancelled
from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.services.answer_stream import AnswerStreamGuard
from backend.services.coaching import CoachingResult, CoachingService, PROVIDER_BLOCK_MESSAGE
from backend.services.groq_client import GroqClient, GenerationProviderError
from backend.services.response_safety import SAFE_RESPONSE


def sse(*items):
    return "".join("data: " + (item if isinstance(item, str) else json.dumps(item)) + "\n\n" for item in items)


def delta(text=None, finish=None, **extra):
    return {"choices": [{"delta": {"content": text, **extra}, "finish_reason": finish}]}


def test_real_groq_service_yields_provider_deltas_and_ignores_reasoning():
    wire = sse(delta("Talk gently. ", reasoning="PRIVATE_REASONING"), delta("Pause and listen."),
               delta(finish="stop"), "[DONE]")
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=wire, headers={"Content-Type": "text/event-stream"})

    client = GroqClient("PRIVATE_KEY", transport=httpx.MockTransport(respond))
    chunks = []
    try:
        result = CoachingService(provider="groq", client=client, model="qwen/qwen3.8-27b").generate(
            "How can I encourage babbling?", 6, None, [], on_delta=chunks.append,
        )
    finally:
        client.close()
    assert chunks == ["Talk gently. ", "Pause and listen."]
    assert result.answer == "".join(chunks)
    assert requests[0]["stream"] is True
    assert requests[0]["include_reasoning"] is False


@pytest.mark.parametrize("wire", [
    sse(delta("Unfinished")), sse(delta("Unfinished"), "[DONE]"),
    sse(delta("Unfinished"), delta(finish="length"), "[DONE]"),
    "data: not-json\n\n", sse({"error": {"message": "PRIVATE_CONTENT"}}),
])
def test_truncated_or_malformed_provider_stream_is_never_successful(wire):
    client = GroqClient("test-key", transport=httpx.MockTransport(lambda _: httpx.Response(200, text=wire)))
    try:
        with pytest.raises(GenerationProviderError) as error:
            list(client.generate_stream(model="qwen/qwen3.8-27b", contents="test", config=SimpleNamespace(system_instruction="test", temperature=.2)))
        assert "PRIVATE_CONTENT" not in str(error.value)
    finally:
        client.close()


def test_provider_refusal_discards_the_aggregated_stream_result():
    wire = sse(delta("A benign opening. "), delta(finish="content_filter"), "[DONE]")
    client = GroqClient("test-key", transport=httpx.MockTransport(lambda _: httpx.Response(200, text=wire)))
    try:
        result = CoachingService(provider="groq", client=client, model="qwen/qwen3.8-27b").generate(
            "How can I encourage babbling?", 6, None, [], on_delta=lambda _: None)
    finally:
        client.close()
    assert result.blocked and result.answer == PROVIDER_BLOCK_MESSAGE


def test_gemini_uses_streaming_and_closes_its_iterator():
    finished = []

    def chunks(**kwargs):
        assert kwargs["config"].http_options.timeout == 45000
        try:
            yield SimpleNamespace(text="Talk gently. ", candidates=[])
            yield SimpleNamespace(text="Pause.", candidates=[SimpleNamespace(finish_reason="STOP")])
        finally:
            finished.append(True)

    client = SimpleNamespace(models=SimpleNamespace(generate_content_stream=chunks))
    seen = []
    result = CoachingService(provider="gemini", client=client, model="test-model").generate(
        "How can I encourage babbling?", 6, None, [], on_delta=seen.append)
    assert result.answer == "Talk gently. Pause."
    assert seen == ["Talk gently. ", "Pause."] and finished == [True]


def test_partial_model_failure_does_not_start_a_fallback_and_concatenate_answers():
    calls = []

    def chunks(**kwargs):
        calls.append(kwargs["model"])
        yield SimpleNamespace(text="Talk gently. ", candidates=[])
        raise GenerationProviderError(429)

    client = SimpleNamespace(models=SimpleNamespace(generate_content_stream=chunks))
    with pytest.raises(GenerationProviderError):
        CoachingService(provider="gemini", client=client, model="primary", fallback_model="fallback").generate(
            "How can I encourage babbling?", 6, None, [], on_delta=lambda _: None)
    assert calls == ["primary"]


def test_sentence_guard_does_not_release_dose_split_across_chunks():
    emitted = []
    guard = AnswerStreamGuard("How can I encourage babbling?", 6, [], [], lambda *event: emitted.append(event))
    for text in ("Talk gently. ", "Give 5 ", "mg medicine. "):
        guard.append(text)
    assert emitted == [("delta", {"text": "Talk gently. "})]


def test_care_specific_conditions_wait_for_complete_answer_validation():
    guard = AnswerStreamGuard("What food can I give my six-month-old baby?", 6, [], [], Mock())
    assert guard.hold
    guard.append("Offer a food. ")
    guard.emit.assert_not_called()


@pytest.fixture
def stream_api(client, monkeypatch):
    data, coaching, retrieval = Mock(), Mock(), Mock()
    data.get_child.return_value = {"age_months": 6, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.get_conversation.return_value = {"messages": []}
    data.save_conversation_turn.return_value = "answer-1"
    retrieval.retrieve.return_value = []

    def generate(*args, on_delta=None, **kwargs):
        if on_delta:
            on_delta("Talk gently. ")
            on_delta("Pause and listen.")
        return CoachingResult("Talk gently. Pause and listen.", [], answer_basis="general_information")

    coaching.generate.side_effect = generate
    monkeypatch.setitem(client.app.dependency_overrides, require_authenticated_user, lambda: {"uid": "account"})
    monkeypatch.setitem(client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    monkeypatch.setitem(client.app.dependency_overrides, get_coaching_service, lambda: coaching)
    monkeypatch.setitem(client.app.dependency_overrides, get_retrieval_service, lambda: retrieval)
    return SimpleNamespace(client=client, data=data, coaching=coaching)


def post_stream(c, **changes):
    response = c.client.post("/coach", headers={"Accept": "text/event-stream"}, json={
        "child_id": "child", "conversation_id": "chat-1", "question": "How can I encourage babbling?", **changes})
    events = []
    for frame in response.text.split("\n\n"):
        if frame.startswith("event:"):
            header, value = frame.split("\n", 1)
            events.append((header[7:], json.loads(value[6:])))
    return response, events


def test_stream_delivers_checked_text_before_ready_and_completion_after_storage(stream_api):
    c = stream_api
    response, events = post_stream(c)
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Accel-Buffering"] == "no"
    kinds = [event[0] for event in events]
    assert kinds.index("delta") < kinds.index("ready") < kinds.index("done")
    assert events[-1][1]["response"]["message_id"] == "answer-1"
    assert "first_answer" in events[-1][1]["timings_ms"]
    c.data.save_conversation_turn.assert_called_once()


def test_unsafe_completion_replaces_preview_and_only_safe_answer_is_saved(stream_api):
    c = stream_api

    def unsafe(*args, on_delta, **kwargs):
        for text in ("Talk gently. ", "Give 5 ", "mg medicine. "):
            on_delta(text)
        return CoachingResult("Talk gently. Give 5 mg medicine.", [])

    c.coaching.generate.side_effect = unsafe
    response, events = post_stream(c)
    assert "Give 5" not in response.text
    assert events[-1][1]["response"]["answer"] == SAFE_RESPONSE
    assert events[-1][1]["response"]["status"] == "safety_blocked"
    assert c.data.save_conversation_turn.call_args.args[-1]["text"] == SAFE_RESPONSE


def test_generation_failure_has_no_done_or_saved_partial_text(stream_api):
    c = stream_api

    def broken(*args, on_delta, **kwargs):
        on_delta("Talk gently. ")
        raise GenerationProviderError(503)

    c.coaching.generate.side_effect = broken
    _, events = post_stream(c)
    assert events[-1][0] == "error" and events[-1][1]["status"] == 503
    assert not any(kind == "done" for kind, _ in events)
    c.data.save_conversation_turn.assert_not_called()


def test_save_failure_never_confirms_ready_answer_as_saved(stream_api):
    c = stream_api
    c.data.save_conversation_turn.side_effect = RuntimeError("PRIVATE_STORAGE_DETAILS")
    response, events = post_stream(c)
    assert any(kind == "ready" for kind, _ in events)
    assert events[-1][0] == "error" and events[-1][1]["status"] == 503
    assert not any(kind == "done" for kind, _ in events)
    assert "PRIVATE_STORAGE_DETAILS" not in response.text


def test_urgent_fixed_reply_streams_before_save_and_never_calls_model(stream_api):
    c = stream_api
    _, events = post_stream(c, question="My baby is not breathing")
    assert events[-1][1]["response"]["status"] == "escalated"
    assert [kind for kind, _ in events].index("ready") < [kind for kind, _ in events].index("done")
    c.coaching.generate.assert_not_called()


def test_cross_provider_stream_restart_saves_only_the_backup_answer(stream_api, monkeypatch):
    from backend.services.provider_failover import ProviderFailoverService

    c = stream_api
    primary, backup = Mock(model="primary"), Mock(model="backup")

    def limited(*args, on_delta, **kwargs):
        on_delta("Old checked preview. ")
        raise GenerationProviderError(429)

    def available(*args, on_delta, **kwargs):
        on_delta("Talk gently. ")
        return CoachingResult("Talk gently. Pause and listen.", [], answer_basis="general_information")

    primary.generate.side_effect = limited
    backup.generate.side_effect = available
    router = ProviderFailoverService(services={"groq": primary, "gemini": backup}, primary="groq")
    monkeypatch.setitem(c.client.app.dependency_overrides, get_coaching_service, lambda: router)
    _, events = post_stream(c)
    kinds = [kind for kind, _ in events]
    assert kinds.index("delta") < kinds.index("reset") < kinds.index("ready") < kinds.index("done")
    final = events[-1][1]["response"]
    assert final["answer"] == "Talk gently. Pause and listen."
    assert "Old checked preview" not in c.data.save_conversation_turn.call_args.args[-1]["text"]
    c.data.save_conversation_turn.assert_called_once()
    assert not any(kind == "error" for kind, _ in events)


def test_both_providers_limited_emit_only_generic_stream_error(stream_api, monkeypatch):
    from backend.services.provider_failover import ProviderFailoverService

    c = stream_api
    primary, backup = Mock(model="primary"), Mock(model="backup")
    for service in (primary, backup):
        service.generate.side_effect = GenerationProviderError(429)
    router = ProviderFailoverService(services={"groq": primary, "gemini": backup}, primary="groq")
    monkeypatch.setitem(c.client.app.dependency_overrides, get_coaching_service, lambda: router)
    response, events = post_stream(c)
    assert events[-1][0] == "error" and events[-1][1]["status"] == 503
    assert "quota" not in response.text.lower() and "exhausted" not in response.text.lower()
    c.data.save_conversation_turn.assert_not_called()


@pytest.mark.asyncio
async def test_disconnected_stream_cancels_pending_operation():
    stream = CoachingStream(Request({"type": "http", "state": {}}))
    cancelled = asyncio.Event()

    async def operation(output):
        try:
            await output.send("delta", {"text": "Talk gently. "})
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    iterator = stream.response(operation).body_iterator
    assert "status" in await anext(iterator)
    assert "delta" in await anext(iterator)
    await iterator.aclose()
    assert stream.cancelled.is_set() and cancelled.is_set()


@pytest.mark.asyncio
async def test_cancel_unblocks_worker_waiting_on_bounded_queue():
    stream = CoachingStream(Request({"type": "http", "state": {}}))
    for _ in range(16):
        await stream.send("status", {"phase": "writing"})
    task = asyncio.create_task(asyncio.to_thread(stream.send_from_worker, "delta", {"text": "Talk gently. "}))
    await asyncio.sleep(.02)
    stream.cancelled.set()
    with pytest.raises(StreamCancelled):
        await asyncio.wait_for(task, timeout=2)


@pytest.mark.parametrize("question,age,fragments", [
    ("Suggest texture play for my child.", 17, ["Offer a smooth ", "stone and paper bag. "]),
    ("My baby is learning to drink from an open cup.", 8, ["Practise pouring ", "bath water into a cup. "]),
    ("Can I pack cut fruit overnight without a refrigerator?", 11,
     ["Put cut fruit in a sealed bag ", "overnight without cooling. "]),
])
def test_new_audit_failures_are_not_released_as_streamed_previews(question, age, fragments):
    emitted = []
    guard = AnswerStreamGuard(question, age, [], [], lambda *event: emitted.append(event))
    for fragment in fragments:
        guard.append(fragment)
    assert not emitted
