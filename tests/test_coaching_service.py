from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievedPassage
from backend.core.config import settings
from unittest.mock import MagicMock

import pytest
from google.genai import errors


def test_gemini_client_has_timeout_and_no_automatic_retries(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr("backend.services.coaching.genai.Client", factory)
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_SECONDS", 30)
    service = CoachingService(api_key="test-key")
    assert service.client is factory.return_value
    assert service.client is factory.return_value
    factory.assert_called_once()
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 30000
    assert options.retry_options.attempts == 1


@pytest.mark.parametrize("timeout", [0, -1, 121, True, 2.5])
def test_invalid_generation_timeout_does_not_create_client(monkeypatch, timeout):
    factory = MagicMock()
    monkeypatch.setattr("backend.services.coaching.genai.Client", factory)
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_SECONDS", timeout)
    with pytest.raises(ValueError, match="GEMINI_TIMEOUT_SECONDS"):
        _ = CoachingService(api_key="test-key").client
    factory.assert_not_called()


@pytest.mark.parametrize("code,expected_error", [(504, TimeoutError), (503, errors.ServerError)])
def test_generation_maps_only_gateway_timeout_to_timeout_error(code, expected_error):
    client = MagicMock()
    client.models.generate_content.side_effect = errors.ServerError(
        code, {"error": {"code": code, "message": "Service error"}},
    )
    passage = RetrievedPassage(
        "p1", "Talk during feeding.", "Feeding", "Reference", 1,
        "https://example.test", 0.8, "6-8 months", ["feeding"],
    )
    with pytest.raises(expected_error):
        CoachingService(client=client).generate("Feeding ideas", 6, "feeding", [passage])
    client.models.generate_content.assert_called_once()


class FakeResponse:
    text = "Try talking about what you are doing during feeding. Pause and respond to your baby's sounds."


class FakeModels:
    def __init__(self):
        self.request = None

    def generate_content(self, **kwargs):
        self.request = kwargs
        return FakeResponse()


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


def test_coaching_service_includes_only_retrieved_passages_in_prompt():
    client = FakeClient()
    passage = RetrievedPassage(
        passage_id="passage-1", text="Talk with your baby during feeding.", title="Talk during feeding",
        source_title="Reach Up", pdf_page=41, source_url="https://example.test/source", score=0.8,
        source_age_label="6-8 months", routines=["feeding"],
    )

    result = CoachingService(client=client).generate("How can I talk at feeding time?", 6, "feeding", [passage])

    assert result.answer.startswith("Try talking")
    assert result.passages == [passage]
    assert "Talk with your baby during feeding" in client.models.request["contents"]
    assert "Do not diagnose" in client.models.request["contents"]


def test_coaching_service_returns_a_safe_message_when_no_passage_matches():
    result = CoachingService(client=FakeClient()).generate("How do I treat a fever?", 6, None, [])

    assert result.passages == []
    assert "health worker" in result.answer
