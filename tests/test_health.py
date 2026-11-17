"""Both liveness-route aliases report that the application is running."""
import pytest
from types import SimpleNamespace

from backend.main import app


@pytest.mark.parametrize("path", ["/health/live", "/api/v1/health/live"])
def test_health_live(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/health/ready", "/api/v1/health/ready"])
def test_health_ready(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_readiness_reads_current_reference_availability_without_calling_network(client, monkeypatch):
    reference_service = SimpleNamespace(readiness=False)
    monkeypatch.setattr(app.state, "retrieval_service", reference_service, raising=False)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    reference_service.readiness = True
    assert client.get("/health/ready").json()["status"] == "ok"
