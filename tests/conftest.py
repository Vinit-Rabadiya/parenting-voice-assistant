import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# set test environment variables so tests can run on their own.
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("FIREBASE_ADMIN_KEY_PATH", ".secrets/firebase-admin.json")


@pytest.fixture(scope="session")
def mock_firebase_app():
    """Provides a mocked Firebase Admin application fixture for local test execution."""
    mock_app = MagicMock()
    with patch("backend.core.firebase.initialize_firebase", return_value=mock_app):
        with patch("firebase_admin.delete_app"):
            yield mock_app


@pytest.fixture
def client(mock_firebase_app):
    """Provides a FastAPI TestClient fixture configured with mocked application lifespan."""
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client
