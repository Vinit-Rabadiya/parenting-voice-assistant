from unittest.mock import MagicMock
import pytest

from backend.services.retrieval import RetrievalService, is_age_eligible


@pytest.mark.parametrize("metadata", [
    {"review_status": "candidate_not_expert_validated"},
    {"release_status": "blocked_pending_health_review"},
    {"clinical_review_required": True},
    {"clinical_review_required": "false"},
    {"clinical_review_required": 0},
])
def test_chat_retrieval_excludes_unapproved_candidate_metadata(metadata):
    point = MagicMock(id="p1", score=0.8, payload={
        "passage_id": "p1", "text": "Unapproved reference.",
        "source_age": {"min_months": 0, "max_months_exclusive": 12}, **metadata,
    })
    client = MagicMock()
    client.query_points.return_value.points = [point]
    assert RetrievalService(client=client).retrieve("feeding", 6) == []
    review = RetrievalService(client=client, collection_name="separate-review", allow_candidate_content=True)
    assert review.retrieve("feeding", 6)[0].passage_id == "p1"


def test_candidate_evaluation_cannot_use_the_application_collection():
    from backend.core.config import settings

    with pytest.raises(ValueError, match="separate evaluation collection"):
        RetrievalService(collection_name=settings.QDRANT_COLLECTION, allow_candidate_content=True)
    with pytest.raises(ValueError, match="boolean"):
        RetrievalService(collection_name="review", allow_candidate_content="false")


def test_candidate_evaluation_still_enforces_age_and_routine_filters():
    point = MagicMock(id="p1", score=0.8, payload={
        "passage_id": "p1", "text": "Review-only reference.", "routines": ["play"],
        "source_age": {"min_months": 6, "max_months_exclusive": 12},
        "review_status": "candidate_not_expert_validated",
    })
    client = MagicMock()
    client.query_points.return_value.points = [point]
    service = RetrievalService(client=client, collection_name="separate-review", allow_candidate_content=True)
    assert service.retrieve("feeding", 3) == []
    assert service.retrieve("feeding", 6, "feeding") == []


@pytest.mark.parametrize("source_age", [
    None, [], "6-8 months", {}, {"label": "unknown"},
    {"minimum_age": 0, "maximum_age": 24},
    {"min_months": 0},
    {"min_months": None, "max_months_exclusive": 9},
    {"min_months": "6", "max_months_exclusive": 9},
    {"min_months": True, "max_months_exclusive": 9},
    {"min_months": -1, "max_months_exclusive": 9},
    {"min_months": 9, "max_months_exclusive": 6},
    {"min_days": 0, "max_days_exclusive": 0},
    {"min_days": 7, "max_months_exclusive": None},
    {"min_days": 7, "max_months_exclusive": 9},
    {"min_months": 0, "max_months_exclusive": 9, "min_days": 0},
])
def test_age_eligibility_fails_closed_for_invalid_metadata(source_age):
    assert is_age_eligible(source_age, 7.0) is False


@pytest.mark.parametrize("age", [None, "7", True, -1, float("nan"), float("inf")])
def test_age_eligibility_rejects_invalid_child_age(age):
    assert is_age_eligible({"min_months": 0, "max_months_exclusive": 9}, age) is False


def test_retrieval_excludes_missing_and_unknown_age_metadata():
    missing = MagicMock(payload={"text": "Missing age"})
    unknown = MagicMock(payload={"text": "Unknown age", "source_age": {"label": "all"}})
    client = MagicMock()
    client.query_points.return_value.points = [missing, unknown]
    assert RetrievalService(client=client).retrieve("play", child_age_months=7) == []


@pytest.mark.parametrize("conditions", [["Baby can retain feeds"], "not-a-list", [None]])
def test_retrieval_preserves_valid_applicability_conditions_and_rejects_invalid_metadata(conditions):
    point = MagicMock(id="p1", score=0.8, payload={
        "passage_id": "p1", "text": "Try supported care.",
        "source_age": {"min_months": 0, "max_months_exclusive": 12},
        "applicability_conditions": conditions,
    })
    client = MagicMock()
    client.query_points.return_value.points = [point]
    results = RetrievalService(client=client).retrieve("feeding", child_age_months=6)
    if isinstance(conditions, list) and all(isinstance(value, str) for value in conditions):
        assert results[0].applicability_conditions == conditions
    else:
        assert results == []


def test_is_age_eligible_first_week():
    # check 0 to 7 days newborn range.
    source_age = {"label": "birth up to 1 week", "min_days": 0, "max_days_exclusive": 7}
    assert is_age_eligible(source_age, child_age_months=0.1) is True
    assert is_age_eligible(source_age, child_age_months=0.5) is False


def test_exact_days_override_legacy_month_conversion():
    first_week = {"min_days": 0, "max_days_exclusive": 7}
    following_band = {"min_days": 7, "max_months_exclusive": 6}
    assert is_age_eligible(first_week, 0, child_age_days=6) is True
    assert is_age_eligible(first_week, 0, child_age_days=7) is False
    assert is_age_eligible(following_band, 0, child_age_days=7) is True
    assert is_age_eligible(following_band, 6, child_age_days=181) is False


def test_is_age_eligible_mixed_unit():
    # check 7 days up to 6 months mixed-unit range.
    source_age = {"label": "1 week up to 6 months", "min_days": 7, "max_months_exclusive": 6}
    assert is_age_eligible(source_age, child_age_months=0.1) is False
    assert is_age_eligible(source_age, child_age_months=2.0) is True
    assert is_age_eligible(source_age, child_age_months=7.0) is False


def test_is_age_eligible_month_band():
    # check 6 to 8 months inclusive range.
    source_age = {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9}
    assert is_age_eligible(source_age, child_age_months=5.9) is False
    assert is_age_eligible(source_age, child_age_months=6.0) is True
    assert is_age_eligible(source_age, child_age_months=7.5) is True
    assert is_age_eligible(source_age, child_age_months=8.9) is True
    assert is_age_eligible(source_age, child_age_months=9.0) is False


def test_is_age_eligible_open_ended():
    # check open-ended upper boundary.
    source_age = {"label": "2 years and older", "min_months": 24, "max_months_exclusive": None}
    assert is_age_eligible(source_age, child_age_months=23.5) is False
    assert is_age_eligible(source_age, child_age_months=24.0) is True
    assert is_age_eligible(source_age, child_age_months=30.0) is True


def test_retrieval_service_filters_passages_by_age():
    mock_point_1 = MagicMock()
    mock_point_1.id = "p1"
    mock_point_1.score = 0.85
    mock_point_1.payload = {
        "passage_id": "p1",
        "title": "Newborn feeding",
        "text": "Feed on cue.",
        "source_title": "CCD",
        "pdf_page": 2,
        "source_url": "https://example.org",
        "source_age": {"label": "birth up to 1 week", "min_days": 0, "max_days_exclusive": 7},
        "routines": ["feeding"],
    }

    mock_point_2 = MagicMock()
    mock_point_2.id = "p2"
    mock_point_2.score = 0.80
    mock_point_2.payload = {
        "passage_id": "p2",
        "title": "Solid food introduction",
        "text": "Introduce mashed foods.",
        "source_title": "Reach Up",
        "pdf_page": 10,
        "source_url": "https://example.org",
        "source_age": {"label": "6-8 months", "min_months": 6, "max_months_exclusive": 9},
        "routines": ["feeding"],
    }

    mock_client = MagicMock()
    mock_client.query_points.return_value = MagicMock(points=[mock_point_1, mock_point_2])

    service = RetrievalService(client=mock_client)

    # p1 is filtered out for a 7-month-old child, only p2 is retained.
    results = service.retrieve("food and feeding", child_age_months=7.0, limit=2)
    assert len(results) == 1
    assert results[0].passage_id == "p2"
    assert results[0].source_age_label == "6-8 months"
