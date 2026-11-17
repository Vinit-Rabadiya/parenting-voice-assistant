"""Shared service ownership, lazy clients and failure-safe application cleanup."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

from anyio import CancelScope, fail_after, to_thread
from fastapi import FastAPI, HTTPException, Request
import pytest

from backend.api.dependencies import get_coaching_service, get_retrieval_service
from backend.core.config import settings
from backend.main import lifespan, warm_references
from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievalService


@pytest.fixture(params=["coaching", "retrieval"])
def lazy_service(request, monkeypatch):
    client = Mock()
    factory = Mock(return_value=client)
    if request.param == "coaching":
        monkeypatch.setattr("backend.services.coaching.genai.Client", factory)
        service_type, arguments = CoachingService, {"api_key": "test-key"}
    else:
        monkeypatch.setattr("backend.services.retrieval.QdrantClient", factory)
        service_type, arguments = RetrievalService, {"url": "https://cluster.example.test", "api_key": "test-key"}

    def build(**options):
        return service_type(**arguments, **options)

    return SimpleNamespace(service=build(), build=build, factory=factory, client=client)


def test_simultaneous_first_use_creates_one_reused_client(lazy_service):
    ready, started, release = Barrier(9), Event(), Event()

    def construct(**kwargs):
        started.set()
        assert release.wait(5)
        return lazy_service.client

    def access():
        ready.wait(timeout=5)
        return lazy_service.service.client

    lazy_service.factory.side_effect = construct
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(access) for _ in range(8)]
        try:
            ready.wait(timeout=5)
            assert started.wait(5)
        finally:
            release.set()
        assert all(future.result(timeout=5) is lazy_service.client for future in futures)
    lazy_service.factory.assert_called_once()
    lazy_service.service.close()
    lazy_service.service.close()
    lazy_service.client.close.assert_called_once()


def test_client_initialization_failure_can_retry_without_caching_failure(lazy_service):
    lazy_service.factory.side_effect = [RuntimeError("initialization failed"), lazy_service.client]
    with pytest.raises(RuntimeError, match="initialization failed"):
        lazy_service.service.client
    assert lazy_service.service.client is lazy_service.client
    assert lazy_service.factory.call_count == 2
    lazy_service.service.close()
    lazy_service.client.close.assert_called_once()


def test_closing_an_unused_service_does_not_initialize_a_client(lazy_service):
    lazy_service.service.close()
    lazy_service.service.close()
    lazy_service.factory.assert_not_called()
    with pytest.raises(RuntimeError, match="service is closed"):
        lazy_service.service.client
    lazy_service.factory.assert_not_called()


def test_injected_clients_remain_owned_by_the_caller(lazy_service):
    borrowed = Mock()
    service = lazy_service.build(client=borrowed)
    assert service.client is borrowed
    service.close()
    borrowed.close.assert_not_called()
    with pytest.raises(RuntimeError, match="service is closed"):
        service.client


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "test-model")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODEL", "")
    monkeypatch.setattr(settings, "QDRANT_URL", "https://cluster.example.test")
    monkeypatch.setattr(settings, "QDRANT_API_KEY", "test-key")
    firebase = Mock()
    initialize = Mock(return_value=firebase)
    delete = Mock()
    speech = Mock()
    gemini = Mock(return_value=Mock())
    qdrant = Mock(return_value=Mock())
    monkeypatch.setattr("backend.main.initialize_firebase", initialize)
    monkeypatch.setattr("backend.main.firebase_admin.delete_app", delete)
    monkeypatch.setattr("backend.main.SpeechService", speech)
    monkeypatch.setattr("backend.services.coaching.genai.Client", gemini)
    monkeypatch.setattr("backend.services.retrieval.QdrantClient", qdrant)
    return SimpleNamespace(app=FastAPI(), firebase=firebase, initialize=initialize,
                           delete=delete, speech=speech, gemini=gemini, qdrant=qdrant)


def assert_services_released(app):
    for name in ("request_admission", "coaching_service", "retrieval_service", "speech_service", "speech_limiter",
                 "caregiver_data_service", "account_security_service", "auth_session_cache", "firebase"):
        assert not hasattr(app.state, name), name


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["development", "production"])
async def test_lifespan_owns_shared_wrappers_and_closes_used_clients(application, monkeypatch, mode):
    monkeypatch.setattr(settings, "APP_ENV", mode)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.test"])
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", True)
    request = Request({"type": "http", "app": application.app})
    async with lifespan(application.app):
        coaching, retrieval = get_coaching_service(request), get_retrieval_service(request)
        assert get_coaching_service(request) is coaching
        assert get_retrieval_service(request) is retrieval
        application.gemini.assert_not_called()
        application.qdrant.assert_not_called()
        assert coaching.client is application.gemini.return_value
        assert retrieval.client is application.qdrant.return_value
        application.app.state.caregiver_data_service = object()
    application.gemini.return_value.close.assert_called_once()
    application.qdrant.return_value.close.assert_called_once()
    application.delete.assert_called_once_with(application.firebase)
    assert_services_released(application.app)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["development", "production"])
@pytest.mark.parametrize("field,value", [
    ("GEMINI_API_KEY", None), ("GEMINI_API_KEY", " \t"),
    ("GEMINI_MODEL", " "), ("GEMINI_FALLBACK_MODEL", None),
])
async def test_invalid_generation_settings_fail_before_initialization(application, monkeypatch, mode, field, value):
    monkeypatch.setattr(settings, "APP_ENV", mode)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.test"])
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", True)
    monkeypatch.setattr(settings, field, value)
    with pytest.raises(ValueError, match=field):
        async with lifespan(application.app):
            pytest.fail("Invalid generation settings must not start serving requests.")
    application.initialize.assert_not_called()
    application.speech.assert_not_called()
    assert_services_released(application.app)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["CoachingService", "RetrievalService", "SpeechService"])
async def test_partial_startup_failure_releases_previously_created_services(application, monkeypatch, stage):
    monkeypatch.setattr("backend.main." + stage, Mock(side_effect=RuntimeError("startup failed")))
    with pytest.raises(RuntimeError, match="startup failed"):
        async with lifespan(application.app):
            pytest.fail("Partial startup must not serve requests.")
    application.gemini.assert_not_called()
    application.qdrant.assert_not_called()
    application.delete.assert_called_once_with(application.firebase)
    assert_services_released(application.app)


@pytest.mark.asyncio
async def test_cleanup_failure_is_redacted_and_does_not_skip_other_services(application, caplog):
    application.qdrant.return_value.close.side_effect = RuntimeError("PRIVATE_CONNECTION_DETAILS")
    async with lifespan(application.app):
        application.app.state.coaching_service.client
        application.app.state.retrieval_service.client
    application.gemini.return_value.close.assert_called_once()
    application.delete.assert_called_once_with(application.firebase)
    assert "service_cleanup service=retrieval_service error_type=RuntimeError" in caplog.text
    assert "PRIVATE_CONNECTION_DETAILS" not in caplog.text
    assert_services_released(application.app)


@pytest.mark.asyncio
async def test_restarting_lifespan_creates_fresh_service_wrappers(application):
    async with lifespan(application.app):
        previous = application.app.state.coaching_service
        previous_sessions = application.app.state.auth_session_cache
    async with lifespan(application.app):
        assert application.app.state.coaching_service is not previous
        assert application.app.state.auth_session_cache is not previous_sessions
        assert previous_sessions._closed
        with pytest.raises(RuntimeError, match="service is closed"):
            previous.client
    assert application.delete.call_count == 2
    application.gemini.assert_not_called()
    application.qdrant.assert_not_called()



@pytest.mark.asyncio
async def test_lifespan_cancellation_still_closes_clients_and_firebase(application):
    with CancelScope() as scope:
        async with lifespan(application.app):
            application.app.state.coaching_service.client
            application.app.state.retrieval_service.client
            scope.cancel()
    application.gemini.return_value.close.assert_called_once()
    application.qdrant.return_value.close.assert_called_once()
    application.delete.assert_called_once_with(application.firebase)
    assert_services_released(application.app)


@pytest.mark.parametrize("dependency", [get_coaching_service, get_retrieval_service])
def test_dependencies_do_not_create_services_outside_lifespan(dependency):
    request = Request({"type": "http", "app": FastAPI()})
    with pytest.raises(HTTPException) as error:
        dependency(request)
    assert error.value.status_code == 503
    assert error.value.detail == "Guidance is unavailable. Please try again."


@pytest.mark.asyncio
async def test_optional_reference_warmup_does_not_block_startup(application, monkeypatch):
    started, release, finished = Event(), Event(), Event()
    monkeypatch.setattr(settings, "QDRANT_WARMUP_ENABLED", True)

    def warmup(self, **kwargs):
        started.set()
        try:
            assert release.wait(2)
            return {"status": "ready"}
        finally:
            finished.set()

    monkeypatch.setattr(RetrievalService, "warmup", warmup)
    try:
        with fail_after(1):
            async with lifespan(application.app):
                assert await to_thread.run_sync(started.wait, 0.5)
                assert not finished.is_set()
                release.set()
                assert await to_thread.run_sync(finished.wait, 0.5)
    finally:
        release.set()
    assert_services_released(application.app)


@pytest.mark.asyncio
async def test_warmup_deadline_stops_waiting_for_an_inflight_request(monkeypatch):
    release, finished = Event(), Event()
    monkeypatch.setattr(settings, "QDRANT_WARMUP_TIMEOUT_SECONDS", 0.02)

    def warmup(**kwargs):
        try:
            release.wait(2)
        finally:
            finished.set()

    try:
        with fail_after(0.5):
            await warm_references(SimpleNamespace(warmup=warmup))
        assert not finished.is_set()
    finally:
        release.set()
        assert await to_thread.run_sync(finished.wait, 0.5)
