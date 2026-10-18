from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievedPassage


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
