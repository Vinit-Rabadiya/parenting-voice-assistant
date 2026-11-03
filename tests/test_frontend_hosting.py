"""The optional static host preserves API routing and authentication."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1.router import api_router
from backend.core.frontend import mount_frontend
from backend.core.http_security import configure_http_security


@pytest.fixture
def hosted_client(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Application</h1>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('static fixture');", encoding="utf-8")
    (assets / "index-12345678.js").write_text("console.log('immutable fixture');" * 1000, encoding="utf-8")
    (assets / "index-12345678.css").write_text("body { color: black; }", encoding="utf-8")
    app = FastAPI()
    configure_http_security(app, production=False, allowed_hosts=[])
    mount_frontend(app, api_router, tmp_path)
    with TestClient(app) as client:
        yield client


def test_serves_index_and_built_assets(hosted_client):
    assert hosted_client.get("/").text == "<h1>Application</h1>"
    assert hosted_client.get("/assets/app.js").status_code == 200


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_public_document_allows_origin_referrers_for_firebase_key_restrictions(hosted_client, path):
    response = hosted_client.get(path)
    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "strict-origin"


def test_public_health_route_is_json_not_the_webpage(hosted_client):
    response = hosted_client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/me", "/api/children", "/api/conversations"])
def test_same_origin_private_routes_still_require_authentication(hosted_client, path):
    response = hosted_client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_missing_api_route_and_static_path_do_not_fall_back_to_html(hosted_client):
    assert hosted_client.get("/api/nonexistent").status_code == 404
    assert hosted_client.get("/missing.js").status_code == 404
    assert hosted_client.get("/%2e%2e/requirements.txt").status_code == 404


def test_missing_frontend_build_fails_clearly(tmp_path):
    with pytest.raises(RuntimeError, match="built frontend"):
        mount_frontend(FastAPI(), api_router, tmp_path)


@pytest.mark.parametrize("path", ["/assets/index-12345678.js", "/assets/index-12345678.css"])
def test_only_successful_versioned_assets_are_immutable(hosted_client, path):
    response = hosted_client.get(path)
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    cached = hosted_client.get(path, headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    assert cached.headers["Cache-Control"] == response.headers["Cache-Control"]


@pytest.mark.parametrize("path", ["/", "/index.html", "/assets/app.js", "/assets/missing-12345678.js", "/api/assets/private-12345678.js"])
def test_documents_unversioned_assets_and_errors_are_not_cached(hosted_client, path):
    assert hosted_client.get(path).headers["Cache-Control"] == "no-store"


def test_public_javascript_is_compressed_without_changing_its_content(hosted_client):
    plain = hosted_client.get("/assets/index-12345678.js", headers={"Accept-Encoding": "identity"})
    compressed = hosted_client.get("/assets/index-12345678.js", headers={"Accept-Encoding": "gzip"})
    assert compressed.headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in compressed.headers["Vary"]
    assert compressed.content == plain.content  # TestClient decodes the wire response.
    assert int(compressed.headers["Content-Length"]) < len(plain.content) / 2
    assert "Content-Encoding" not in hosted_client.get("/api/health/live").headers
