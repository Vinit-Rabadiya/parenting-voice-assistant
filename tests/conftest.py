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


CORPUS_PATH = Path(__file__).resolve().parent.parent / "data/processed/rag/passages.jsonl"


def pytest_addoption(parser):
    parser.addoption(
        "--require-corpus", action="store_true", default=False,
        help="Fail before testing if the prepared real passage corpus is missing.",
    )


def pytest_sessionstart(session):
    if session.config.getoption("--require-corpus") and not CORPUS_PATH.is_file():
        raise pytest.UsageError(
            "--require-corpus needs data/processed/rag/passages.jsonl. "
            "Run python -m scripts.prepare_rag_data and "
            "python -m scripts.build_rag_passages with the source PDFs available."
        )


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
    from backend.api.consent import require_processing_consent

    # Existing feature tests assume consent is already granted. Consent tests
    # explicitly remove this override to exercise the actual access policy.
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[require_processing_consent] = lambda: None
    try:
        with patch("backend.main.SpeechService"):
            with TestClient(app) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
