"""Both liveness-route aliases report that the application is running."""
import pytest


@pytest.mark.parametrize("path", ["/health/live", "/api/v1/health/live"])
def test_health_live(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
