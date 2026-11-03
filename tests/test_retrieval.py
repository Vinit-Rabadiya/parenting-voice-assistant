from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from backend.services.retrieval import RetrievalService, is_age_eligible


@pytest.fixture
def cached_retrieval(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("backend.services.retrieval.monotonic", lambda: clock[0])
    point = MagicMock(id="p1", score=0.9, payload={
        "passage_id": "p1", "text": "Public reference text.", "title": "Play together",
        "source_title": "Care reference", "source_url": "https://example.test/care", "pdf_page": 4,
        "source_age": {"min_months": 0, "max_months_exclusive": 25}, "routines": ["play"],
        "applicability_conditions": ["Stay nearby"],
    })
    client = MagicMock()
    client.query_points.return_value.points = [point]
    return RetrievalService(client=client, cache_ttl_seconds=60), client, clock


def test_repeated_retrieval_uses_copied_sources_without_retaining_question(cached_retrieval):
    service, client, _ = cached_retrieval
    first = service.retrieve("PRIVATE_CAREGIVER_MESSAGE", 6, "play", child_age_days=183)
    first[0].text = "CHANGED_BY_CALLER"
    first[0].routines.append("feeding")
    first[0].applicability_conditions.clear()
    second = service.retrieve("PRIVATE_CAREGIVER_MESSAGE", 6, "play", child_age_days=183)
    assert second[0].text == "Public reference text."
    assert second[0].routines == ["play"]
    assert second[0].applicability_conditions == ["Stay nearby"]
    assert second[0].source_url == "https://example.test/care" and second[0].pdf_page == 4
    second[0].text = "ALSO_CHANGED"
    assert service.retrieve("PRIVATE_CAREGIVER_MESSAGE", 6, "play", child_age_days=183)[0].text == "Public reference text."
    assert "PRIVATE_CAREGIVER_MESSAGE" not in repr(service._cache)
    client.query_points.assert_called_once()


@pytest.mark.parametrize("change", [
    {"query": "A different question"}, {"child_age_months": 7}, {"child_age_days": 184},
    {"routine": "feeding"}, {"limit": 2}, {"candidate_limit": 20},
])
def test_cache_separates_complete_query_age_routine_and_search_limits(cached_retrieval, change):
    service, client, _ = cached_retrieval
    options = dict(query="Play ideas", child_age_months=6, routine="play", child_age_days=183)
    service.retrieve(**options)
    service.retrieve(**{**options, **change})
    assert client.query_points.call_count == 2


@pytest.mark.parametrize("attribute,value", [
    ("collection_name", "updated-collection"), ("corpus_revision", "review-2"),
    ("allow_candidate_content", True),
])
def test_collection_revision_and_review_policy_have_separate_cache_entries(cached_retrieval, attribute, value):
    service, client, _ = cached_retrieval
    service.retrieve("Play ideas", 6)
    setattr(service, attribute, value)
    service.retrieve("Play ideas", 6)
    assert client.query_points.call_count == 2


def test_cache_expires_at_deadline_and_does_not_serve_stale_sources_on_error(cached_retrieval):
    service, client, clock = cached_retrieval
    service.retrieve("Play ideas", 6)
    clock[0] += 59.9
    service.retrieve("Play ideas", 6)
    client.query_points.assert_called_once()
    clock[0] += 0.1
    client.query_points.side_effect = RuntimeError("Query unavailable")
    with pytest.raises(RuntimeError, match="Query unavailable"):
        service.retrieve("Play ideas", 6)
    client.query_points.side_effect = None
    assert service.retrieve("Play ideas", 6)
    assert client.query_points.call_count == 3


@pytest.mark.parametrize("empty", [True, False])
def test_empty_or_failed_results_are_not_cached(cached_retrieval, empty):
    service, client, _ = cached_retrieval
    if empty:
        client.query_points.return_value.points = []
        assert service.retrieve("Play ideas", 6) == []
    else:
        client.query_points.side_effect = RuntimeError("Query unavailable")
        with pytest.raises(RuntimeError):
            service.retrieve("Play ideas", 6)
        client.query_points.side_effect = None
    service.retrieve("Play ideas", 6)
    assert client.query_points.call_count == 2


def test_cache_age_filter_preserves_first_week_boundary(cached_retrieval):
    service, client, _ = cached_retrieval
    client.query_points.return_value.points[0].payload["source_age"] = {"min_days": 0, "max_days_exclusive": 7}
    assert service.retrieve("Play ideas", 0, child_age_days=6)
    assert service.retrieve("Play ideas", 0, child_age_days=7) == []
    assert service.retrieve("Play ideas", 0, child_age_days=6)
    assert client.query_points.call_count == 2


def test_cache_evicts_least_recently_used_and_can_be_cleared(cached_retrieval):
    service, client, _ = cached_retrieval
    for number in range(128):
        service.retrieve(f"Play ideas {number}", 6)
    service.retrieve("Play ideas 0", 6)
    service.retrieve("Play ideas 128", 6)
    assert len(service._cache) == 128
    service.retrieve("Play ideas 0", 6)
    assert client.query_points.call_count == 129
    service.retrieve("Play ideas 1", 6)
    assert client.query_points.call_count == 130
    service.clear_cache()
    assert not service._cache
    service.retrieve("Play ideas 0", 6)
    assert client.query_points.call_count == 131


def test_clearing_cache_during_query_prevents_late_repopulation(cached_retrieval):
    service, client, _ = cached_retrieval
    started, release = Event(), Event()
    result = client.query_points.return_value

    def slow_query(**kwargs):
        started.set()
        assert release.wait(3)
        return result

    client.query_points.side_effect = slow_query
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.retrieve, "Play ideas", 6)
        try:
            assert started.wait(3)
            service.clear_cache()
        finally:
            release.set()
        assert pending.result(timeout=3)
    assert not service._cache


def test_warm_cache_is_thread_safe_and_close_removes_sources(cached_retrieval):
    service, client, _ = cached_retrieval
    service.retrieve("Play ideas", 6)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.retrieve("Play ideas", 6), range(12)))
    assert all(result[0].passage_id == "p1" for result in results)
    client.query_points.assert_called_once()
    service.close()
    assert not service._cache
    with pytest.raises(RuntimeError, match="closed"):
        service.retrieve("Play ideas", 6)


def test_cache_can_be_disabled_for_live_evaluations(cached_retrieval):
    _, client, _ = cached_retrieval
    service = RetrievalService(client=client, cache_ttl_seconds=0)
    service.retrieve("Play ideas", 6)
    service.retrieve("Play ideas", 6)
    assert client.query_points.call_count == 2 and not service._cache


@pytest.mark.parametrize("ttl", [-1, float("inf"), float("nan"), True, "60", 301])
def test_cache_duration_is_bounded(ttl):
    with pytest.raises(ValueError, match="TTL"):
        RetrievalService(client=MagicMock(), cache_ttl_seconds=ttl)


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
