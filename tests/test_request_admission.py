"""Processing admission protects shared capacity without persistent usage records."""

import asyncio
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import anyio
from fastapi import FastAPI
import httpx
import pytest

from backend.core.request_admission import AdmissionRejected, RequestAdmission
from backend.core.http_security import HTTPSecurityMiddleware
from backend.core.security import require_authenticated_user
from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.services.coaching import CoachingResult


def test_short_burst_recovers_and_never_retains_raw_identity():
    now = [0.0]
    admission = RequestAdmission(burst=2, clock=lambda: now[0])
    for _ in range(2):
        with admission.processing("PRIVATE_USER"):
            pass
    with pytest.raises(AdmissionRejected):
        with admission.processing("PRIVATE_USER"):
            pass
    now[0] += 3
    with admission.processing("PRIVATE_USER"):
        pass
    with admission.processing("another-user"):
        pass
    assert "PRIVATE_USER" not in repr(admission._buckets)


def test_normal_repeated_use_has_no_hourly_or_daily_quota():
    now = [0.0]
    admission = RequestAdmission(clock=lambda: now[0])
    for _ in range(1000):
        with admission.processing("user"):
            pass
        now[0] += 5


def test_read_bursts_have_separate_capacity_and_recover_quickly():
    now = [0.0]
    admission = RequestAdmission(clock=lambda: now[0])
    for _ in range(32):
        admission.check_read("user")
    with pytest.raises(AdmissionRejected):
        admission.check_read("user")
    # Reading history must not use up the allowance for asking a question.
    with admission.processing("user"):
        pass
    now[0] += 1
    admission.check_read("user")


def test_parallel_work_is_bounded_and_exceptions_release_capacity():
    admission = RequestAdmission(enforce_rate=False, max_active=3, max_per_user=2)
    with ExitStack() as stack:
        stack.enter_context(admission.processing("a"))
        stack.enter_context(admission.processing("a"))
        with pytest.raises(AdmissionRejected):
            stack.enter_context(admission.processing("a"))
        stack.enter_context(admission.processing("b"))
        with pytest.raises(AdmissionRejected):
            stack.enter_context(admission.processing("c"))
    with pytest.raises(RuntimeError):
        with admission.processing("a"):
            raise RuntimeError("Failed operation")
    assert admission._active == {}


def test_admission_memory_is_bounded_and_closed_service_cannot_be_reused():
    admission = RequestAdmission(capacity=5)
    for index in range(30):
        admission.check_write(str(index))
    assert len(admission._buckets) == 5
    admission.close()
    assert not admission._buckets
    with pytest.raises(AdmissionRejected):
        admission.check_write("user")


@pytest.fixture
def guarded(client, monkeypatch):
    data, retrieval, coaching = Mock(), Mock(), Mock()
    data.get_child.return_value = {"age_months": 8, "completed_months": 8, "age_days": 244, "in_scope": True}
    data.create_interaction.return_value = "interaction"
    data.delete_child.return_value = True
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult("Talk gently with your baby.", [], answer_basis="general_information")
    monkeypatch.setattr(client.app.state, "request_admission", RequestAdmission(burst=2))
    for dependency, factory in ((require_authenticated_user, lambda: {"uid": "user"}),
                                (get_caregiver_data_service, lambda: data),
                                (get_retrieval_service, lambda: retrieval),
                                (get_coaching_service, lambda: coaching)):
        monkeypatch.setitem(client.app.dependency_overrides, dependency, factory)
    return client, data, coaching


@pytest.mark.parametrize("path", ["/coach", "/api/v1/coach"])
def test_processing_burst_is_rejected_before_database_or_provider_work(guarded, path):
    client, data, coaching = guarded
    payload = {"child_id": "child", "question": "How can we take turns making gentle sounds?"}
    assert client.post(path, json=payload).status_code == 200
    assert client.post(path, json=payload).status_code == 200
    rejected = client.post(path, json=payload)
    assert rejected.status_code == 429 and rejected.headers["Retry-After"] == "3"
    assert coaching.generate.call_count == data.get_child.call_count == 2


def test_stream_completion_and_provider_failure_release_processing_slot(guarded):
    client, _, coaching = guarded
    payload = {"child_id": "child", "question": "How can I encourage gestures?"}
    response = client.post("/coach", json=payload, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200 and "event: done" in response.text
    assert not client.app.state.request_admission._active
    coaching.generate.side_effect = RuntimeError("Provider unavailable")
    assert client.post("/coach", json=payload).status_code == 502
    assert not client.app.state.request_admission._active


def test_busy_processing_does_not_block_health_or_child_deletion(guarded, monkeypatch):
    client, data, coaching = guarded
    monkeypatch.setattr(client.app.state, "request_admission", RequestAdmission(max_active=1))
    started, release = Event(), Event()

    def generate(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return CoachingResult("Share a quiet moment.", [])

    coaching.generate.side_effect = generate
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(client.post, "/coach", json={"child_id": "child", "question": "Suggest a gentle activity."})
        try:
            assert started.wait(2)
            assert client.post("/coach", json={"child_id": "child", "question": "Another activity?"}).status_code == 429
            assert client.get("/health/live").status_code == 200
            assert client.delete("/children/child").status_code == 204
            data.delete_child.assert_called_once_with("user", "child")
        finally:
            release.set()
        assert request.result(timeout=2).status_code == 200


@pytest.mark.asyncio
async def test_anonymous_upload_capacity_is_rejected_without_buffering_another_body():
    app = FastAPI()
    app.add_middleware(HTTPSecurityMiddleware, max_uploads=1)

    @app.post("/upload")
    def upload():
        return {"ok": True}

    @app.get("/health/live")
    def health():
        return {"ok": True}

    started, release = anyio.Event(), anyio.Event()

    async def slow_body():
        started.set()
        await release.wait()
        yield b"test"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/upload", content=slow_body()))
        try:
            with anyio.fail_after(2):
                await started.wait()
                rejected = await client.post("/upload", content=b"second")
                assert rejected.status_code == 429
                assert rejected.headers["Cache-Control"] == "no-store"
                assert (await client.get("/health/live")).status_code == 200
        finally:
            release.set()
        assert (await first).status_code == 200
        assert (await client.post("/upload", content=b"next")).status_code == 200


@pytest.mark.asyncio
async def test_disconnect_keeps_actual_provider_capacity_reserved_until_worker_finishes():
    from fastapi import Depends, Request
    from backend.api.coaching_stream import CoachingStream
    from backend.api.request_admission import require_processing_slot, run_processing_worker

    started, release, finished = Event(), Event(), Event()
    app = FastAPI()
    admission = RequestAdmission(max_active=1, enforce_rate=False)
    app.state.request_admission = admission
    app.dependency_overrides[require_authenticated_user] = lambda: {"uid": "synthetic-user"}

    def blocking_provider():
        started.set()
        try:
            assert release.wait(5)
        finally:
            finished.set()

    @app.post("/stream", dependencies=[Depends(require_processing_slot)])
    async def endpoint(request: Request):
        async def operation(output):
            return await run_processing_worker(request, "synthetic-user", blocking_provider)
        return CoachingStream(request).response(operation)

    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        while not started.is_set():
            await asyncio.sleep(.001)
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
        "method": "POST", "path": "/stream", "raw_path": b"/stream", "query_string": b"",
        "headers": [], "scheme": "http", "server": ("test", 80), "client": ("test", 1), "root_path": "",
    }
    try:
        await asyncio.wait_for(app(scope, receive, send), timeout=2)
        assert started.is_set() and not finished.is_set()
        assert admission._active == {}  # HTTP dependency has finished cleaning up.
        with pytest.raises(AdmissionRejected):
            with admission.processing("another-user"):
                pass
        with pytest.raises(AdmissionRejected):
            with admission.worker("another-user"):
                pass
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        with anyio.fail_after(1):
            while admission._workers:
                await asyncio.sleep(.001)
    with admission.processing("synthetic-user"):
        pass

