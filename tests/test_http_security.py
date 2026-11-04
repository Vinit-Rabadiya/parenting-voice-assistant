"""HTTP privacy headers and bounded uploads apply before endpoint processing."""

import anyio
import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from unittest.mock import patch
import logging
import json
import time

from backend.core.http_security import (
    HTTPSecurityMiddleware, MAX_BODY_BYTES, MAX_JSON_BYTES, RequestStageTimings,
    configure_http_security,
)


@pytest.fixture
def upload_app():
    app = FastAPI()
    app.add_middleware(HTTPSecurityMiddleware)

    @app.post("/upload")
    async def upload(request: Request):
        return {"size": len(await request.body())}

    return app


@pytest.mark.parametrize("path", ["/children", "/api/v1/conversations?child_id=example", "/me"])
def test_denied_private_responses_cannot_be_cached_or_framed(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_request_duration_includes_authentication_without_logging_identity_or_query(client, caplog):
    def verify(*args, **kwargs):
        time.sleep(0.02)
        return {"uid": "PRIVATE_ACCOUNT", "email_verified": True, "firebase": {}}

    with caplog.at_level(logging.INFO, logger="uvicorn.error.request_timing"):
        with patch("backend.core.security.auth.verify_id_token", side_effect=verify):
            response = client.get("/me?secret=PRIVATE_QUERY", headers={"Authorization": "Bearer PRIVATE_TOKEN"})
    assert response.status_code == 200
    metrics = dict(metric.strip().split(";dur=") for metric in response.headers["Server-Timing"].split(","))
    assert float(metrics["app"]) >= 15
    assert float(metrics["token_verification"]) >= 15
    assert "account_security" in metrics
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 12
    messages = "\n".join(r.message for r in caplog.records if r.name == "uvicorn.error.request_timing")
    assert f"request={request_id}" in messages
    assert "stage=token_verification" in messages and "stage=account_security" in messages
    assert "route=/me status=200" in messages
    assert all(secret not in messages for secret in ("PRIVATE_ACCOUNT", "PRIVATE_QUERY", "PRIVATE_TOKEN"))
    assert all(secret not in response.headers["Server-Timing"]
               for secret in ("PRIVATE_ACCOUNT", "PRIVATE_QUERY", "PRIVATE_TOKEN"))


def test_timing_collector_bounds_names_and_rejects_invalid_durations():
    timings = RequestStageTimings()
    for index in range(1000):
        timings.record(f"PRIVATE_VALUE_{index}", 1)
    for invalid in (-1, float("inf"), float("nan")):
        timings.record("generation", invalid)
    assert timings.header() == ""
    timings.record("generation", .1)
    timings.record("generation", .2)
    assert timings.header() == "generation;dur=300.0"


def test_provider_switch_does_not_sum_two_first_token_measurements():
    timings = RequestStageTimings()
    timings.record("generation_first_token", .1, first=True)
    timings.record("generation_first_token", .4, first=True)
    assert timings.snapshot()["generation_first_token"] == 100


@pytest.mark.parametrize("production", [False, True])
def test_local_capture_is_one_shot_metadata_only_and_disabled_in_production(tmp_path, production):
    app = FastAPI()
    configure_http_security(app, production=production, allowed_hosts=["testserver"],
                            development_timing_directory=tmp_path)

    @app.post("/coach")
    def coach():
        return {"answer": "PRIVATE_ANSWER"}

    flag = tmp_path / "capture-next-coach-timing"
    output = tmp_path / "local-coach-timing.json"
    with TestClient(app, base_url="https://testserver:8000") as client:
        client.post("/coach")
        assert not output.exists()  # No recording unless explicitly armed.
        flag.write_text(json.dumps({"server_port": 8000}), encoding="utf-8-sig")
        client.post("https://testserver:8001/coach")
        assert flag.exists() and not output.exists()
        response = client.post("/coach?private=PRIVATE_QUERY", json={"question": "PRIVATE_QUESTION"},
                               headers={"Authorization": "Bearer PRIVATE_TOKEN"})
        assert response.status_code == 200
        if production:
            assert not output.exists() and flag.exists()
        else:
            assert not flag.exists()
            record = json.loads(output.read_text())
            assert set(record) == {"request_id", "route", "status", "total_ms", "stages_ms"}
            assert record["request_id"] == response.headers["X-Request-ID"]
            assert record["route"] == "/coach" and record["status"] == 200
            assert "PRIVATE" not in output.read_text()
            client.post("/coach")
            assert json.loads(output.read_text()) == record


@pytest.mark.asyncio
async def test_stage_headers_are_isolated_between_overlapping_requests_and_after_errors():
    from asyncio import gather
    from backend.api.v1.endpoints.coaching import timed_stage

    app = FastAPI()
    configure_http_security(app, production=False, allowed_hosts=[])

    @app.post("/coach")
    async def measured(request: Request):
        stage = request.query_params.get("stage")
        if stage:
            with timed_stage(request.state.performance_request_id, stage):
                await anyio.sleep(.01)
                if stage == "response_safety":
                    raise HTTPException(status_code=409)
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first, second = await gather(client.post("/coach?stage=retrieval"), client.post("/coach?stage=generation"))
        assert "retrieval;dur=" in first.headers["Server-Timing"]
        assert "generation;dur=" not in first.headers["Server-Timing"]
        assert "generation;dur=" in second.headers["Server-Timing"]
        assert "retrieval;dur=" not in second.headers["Server-Timing"]
        failed = await client.post("/coach?stage=response_safety")
        assert failed.status_code == 409
        assert "response_safety;dur=" in failed.headers["Server-Timing"]
        clean = await client.post("/coach")
        assert len(clean.headers["Server-Timing"].split(",")) == 1


def test_speech_request_timing_excludes_audio_and_query_text(client, caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error.request_timing"):
        response = client.post("/speech/transcribe?private=PRIVATE_QUERY", content=b"PRIVATE_AUDIO",
                               headers={"Content-Type": "audio/wav"})
    assert response.status_code == 401
    assert "Server-Timing" in response.headers
    assert len(response.headers["X-Request-ID"]) == 12
    messages = "\n".join(r.message for r in caplog.records if r.name == "uvicorn.error.request_timing")
    assert "route=/speech/transcribe status=401" in messages
    assert "PRIVATE_AUDIO" not in messages and "PRIVATE_QUERY" not in messages


def test_https_sets_transport_security_without_redirecting_local_http(upload_app):
    with TestClient(upload_app, base_url="https://example.test") as client:
        response = client.post("/upload", content=b"data")
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
        assert response.headers["Cache-Control"] == "no-store"
    with TestClient(upload_app) as client:
        assert "Strict-Transport-Security" not in client.post("/upload").headers


def test_production_redirects_http_and_rejects_unrecognized_hosts():
    app = FastAPI()
    configure_http_security(app, production=True, allowed_hosts=["api.example.test"])

    @app.get("/private")
    def private():
        return {"status": "example"}

    with TestClient(app, base_url="http://api.example.test", follow_redirects=False) as client:
        response = client.get("/private")
        assert response.status_code == 307
        assert response.headers["Location"] == "https://api.example.test/private"
        assert response.headers["Cache-Control"] == "no-store"
        response = client.get("https://api.example.test/private")
        assert response.status_code == 200
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
        response = client.get("https://unrecognized.test/private")
        assert response.status_code == 400
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("content_type,limit", [("application/json", MAX_JSON_BYTES),
                                               ("audio/wav", MAX_BODY_BYTES)])
def test_request_size_boundaries(upload_app, content_type, limit):
    with TestClient(upload_app) as client:
        response = client.post("/upload", content=b"x" * limit,
                               headers={"Content-Type": content_type})
        assert response.json() == {"size": limit}
        response = client.post("/upload", content=b"x" * (limit + 1),
                               headers={"Content-Type": content_type})
        assert response.status_code == 413
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("length", ["-1", "not-a-number", "1, 2", "9" * 5000])
def test_malformed_content_length_is_rejected(upload_app, length):
    with TestClient(upload_app) as client:
        assert client.post("/upload", content=b"x", headers={"Content-Length": length}).status_code == 400


@pytest.mark.asyncio
async def test_chunked_upload_cannot_bypass_size_limit(upload_app):
    async def chunks():
        yield b"x" * MAX_JSON_BYTES
        yield b"x"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=upload_app), base_url="http://test") as client:
        response = await client.post("/upload", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_slow_upload_has_a_deadline(upload_app, monkeypatch):
    monkeypatch.setattr("backend.core.http_security.BODY_TIMEOUT_SECONDS", 0.01)

    async def chunks():
        yield b"x"
        await anyio.sleep_forever()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=upload_app), base_url="http://test") as client:
        response = await client.post("/upload", content=chunks())
    assert response.status_code == 408


def test_stream_capture_includes_body_and_save_stages_after_headers(tmp_path):
    from types import SimpleNamespace
    from backend.api.coaching_stream import CoachingStream
    from backend.core.http_security import record_request_stage

    app = FastAPI()
    configure_http_security(app, production=False, allowed_hosts=[], development_timing_directory=tmp_path)

    @app.post("/coach")
    async def stream(request: Request):
        async def operation(output):
            await output.send("delta", {"text": "PRIVATE_ANSWER"})
            await anyio.sleep(.01)
            record_request_stage("interaction_save", .001)
            return SimpleNamespace(model_dump=lambda **kwargs: {"answer": "PRIVATE_ANSWER"})
        return CoachingStream(request).response(operation)

    (tmp_path / "capture-next-coach-timing").write_text(json.dumps({"server_port": 8000}))
    with TestClient(app, base_url="http://testserver:8000") as client:
        response = client.post("/coach")
    record = json.loads((tmp_path / "local-coach-timing.json").read_text())
    assert record["stream_outcome"] == "completed"
    assert record["total_ms"] >= 10
    assert "first_answer" in record["stages_ms"]
    assert "interaction_save" in record["stages_ms"]
    assert "interaction_save" not in response.headers["Server-Timing"]
    assert "PRIVATE" not in json.dumps(record)
