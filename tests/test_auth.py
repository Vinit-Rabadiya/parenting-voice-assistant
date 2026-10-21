"""Both account-route aliases reject requests without a login token."""
import pytest


@pytest.mark.parametrize("path", ["/me", "/api/v1/me"])
def test_me_without_token_returns_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."
