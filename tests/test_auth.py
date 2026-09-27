def test_me_without_token_returns_401(client):
    """Verifies that accessing /me without an Authorization header returns HTTP 401."""
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."


def test_me_v1_without_token_returns_401(client):
    """Verifies that accessing /api/v1/me without an Authorization header returns HTTP 401."""
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."
