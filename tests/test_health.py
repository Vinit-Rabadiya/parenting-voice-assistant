def test_health_live(client):
    """Verifies that the root health check endpoint returns HTTP 200 and 'ok' status."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_live_v1(client):
    """Verifies that the versioned v1 health check endpoint returns HTTP 200 and 'ok' status."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
