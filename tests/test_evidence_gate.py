from unittest.mock import MagicMock

import pytest
import httpx

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.coaching import CoachingResult
from backend.services.evidence import select_evidence
from backend.services.retrieval import RetrievedPassage


def passage(score: float, text: str = "Talk with your baby during feeding.") -> RetrievedPassage:
    return RetrievedPassage("p1", text, "Feeding conversation", "Reference", 1,
                            "https://example.test/reference", score, "6-8 months", ["feeding"])


def test_gate_keeps_boundary_and_rejects_invalid_or_empty_evidence():
    accepted = passage(0.50)
    assert select_evidence([passage(0.49), passage(float("nan")), passage(float("inf")),
                            passage(0.9, " "), accepted], 0.50) == [accepted]


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_gate_rejects_invalid_configuration(threshold):
    with pytest.raises(ValueError, match="RETRIEVAL_MIN_SCORE"):
        select_evidence([], threshold)


@pytest.fixture
def services(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "RETRIEVAL_MIN_SCORE", 0.50)
    data, retrieval, coaching = MagicMock(), MagicMock(), MagicMock()
    data.get_child.return_value = {"age_months": 6.0, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.create_interaction.return_value = "interaction-1"
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        require_authenticated_user: lambda: {"uid": "user-1"},
        get_caregiver_data_service: lambda: data,
        get_retrieval_service: lambda: retrieval,
        get_coaching_service: lambda: coaching,
    })
    yield data, retrieval, coaching
    app.dependency_overrides.clear()
    app.dependency_overrides.update(overrides)


@pytest.mark.parametrize("scores", [[], [0.49], [0.20, 0.48]])
def test_no_evidence_skips_generation_and_saves_outcome(client, services, scores):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(score) for score in scores]
    response = client.post("/coach", json={"child_id": "child-1", "question": "Unsupported question"})
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["citations"] == []
    coaching.generate.assert_not_called()
    assert data.create_interaction.call_args.args[-1] == "no_evidence"


def test_only_eligible_evidence_reaches_generation(client, services):
    _, retrieval, coaching = services
    accepted = passage(0.7)
    retrieval.retrieve.return_value = [passage(0.3), accepted]
    coaching.generate.return_value = CoachingResult("Talk with your baby.", [accepted])
    response = client.post("/coach", json={"child_id": "child-1", "question": "How can I talk during feeding?"})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert len(response.json()["citations"]) == 1
    assert coaching.generate.call_args.args[-1] == [accepted]


def test_retrieval_failure_is_not_a_no_evidence_response(client, services):
    _, retrieval, coaching = services
    retrieval.retrieve.side_effect = TimeoutError("Connection timed out")
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 502
    assert "status" not in response.json()
    coaching.generate.assert_not_called()


def test_out_of_scope_profile_never_reaches_retrieval_or_generation(client, services):
    data, retrieval, coaching = services
    data.get_child.return_value = {"age_months": 24.1, "completed_months": 24,
                                   "age_days": 732, "in_scope": False}
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 422
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.create_interaction.assert_not_called()


@pytest.mark.parametrize("error", [TimeoutError("timed out"), httpx.ReadTimeout("timed out")])
def test_generation_timeout_is_not_saved_as_a_no_evidence_answer(client, services, error):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(0.7)]
    coaching.generate.side_effect = error
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 504
    assert response.json()["detail"] == "Guidance generation timed out. Please try again."
    assert "status" not in response.json()
    data.create_interaction.assert_not_called()
