# this file sets up shared test helpers and fake firebase and speech services.
# it is automatically loaded by pytest whenever running tests in the tests/ directory.
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# add project root to python path so test runner finds backend.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# set test environment variables so tests can run on their own.
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("FIREBASE_ADMIN_KEY_PATH", ".secrets/firebase-admin.json")


@pytest.fixture(scope="session")
def mock_firebase_app():
    """Provides a mocked Firebase Admin application fixture for local test execution."""
    mock_app = MagicMock()
    with patch("backend.main.initialize_firebase", return_value=mock_app):
        with patch("firebase_admin.delete_app"):
            yield mock_app


@pytest.fixture
def client(mock_firebase_app):
    """Provides a FastAPI TestClient fixture configured with mocked application lifespan."""
    from backend.main import app

    # replace speech initialization before the test client starts the app.
    with patch("backend.main.SpeechService"):
        with TestClient(app) as test_client:
            yield test_client
