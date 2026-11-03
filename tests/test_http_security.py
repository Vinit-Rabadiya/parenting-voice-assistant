"""HTTP privacy headers and bounded uploads apply before endpoint processing."""

import anyio
import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from unittest.mock import patch
import logging
import time

from backend.core.http_security import (
    HTTPSecurityMiddleware, MAX_BODY_BYTES, MAX_JSON_BYTES, configure_http_security,
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
    assert float(response.headers["Server-Timing"].split("=")[1]) >= 15
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 12
    messages = "\n".join(r.message for r in caplog.records if r.name == "uvicorn.error.request_timing")
    assert f"request={request_id}" in messages
    assert "stage=token_verification" in messages and "stage=account_security" in messages
    assert "route=/me status=200" in messages
    assert all(secret not in messages for secret in ("PRIVATE_ACCOUNT", "PRIVATE_QUERY", "PRIVATE_TOKEN"))


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
