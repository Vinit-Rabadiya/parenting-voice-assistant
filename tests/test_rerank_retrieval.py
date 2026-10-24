from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.services.evidence import select_evidence
from backend.services.retrieval import RetrievalService, RetrievedPassage
from scripts.rerank_retrieval import RerankedRetrieval


def passage(pid, score):
    return RetrievedPassage(pid, "Source text " + pid, "Title", "Reference", None,
                            "https://example.test", score, "6-9 months", ["play"])


def test_reranker_reorders_without_changing_similarity_or_source_objects():
    candidates = [passage("first", 0.8), passage("second", 0.4)]
    retrieval = Mock()
    retrieval.retrieve.return_value = candidates
    model = Mock()
    model.predict.return_value = [-2.0, 5.0]
    service = RerankedRetrieval(retrieval, model=model)
    result = service.retrieve("Play ideas", 6, "play", limit=1, child_age_days=183)
    assert result == [candidates[1]]
    assert result[0].score == 0.4
    assert select_evidence(result, 0.5) == []
    assert candidates[0].score == 0.8
    model.predict.assert_called_once_with(
        [("Play ideas", "Source text first"), ("Play ideas", "Source text second")],
        batch_size=16, show_progress_bar=False)


def test_comparison_keeps_the_same_raw_candidate_budget():
    retrieval = Mock()
    retrieval.retrieve.return_value = []
    model = Mock()
    service = RerankedRetrieval(retrieval, model=model)
    assert service.retrieve("Play", 6, "play", 4, child_age_days=183) == []
    retrieval.retrieve.assert_called_once_with(query="Play", child_age_months=6, routine="play",
                                             limit=20, child_age_days=183, candidate_limit=20)
    model.predict.assert_not_called()
    assert service.last_timings["candidate_count"] == 0


@pytest.mark.parametrize("scores", [[float("nan")], [float("inf")], [], [1.0, 2.0]])
def test_invalid_cross_encoder_output_fails_explicitly(scores):
    retrieval, model = Mock(), Mock()
    retrieval.retrieve.return_value = [passage("one", 0.8)]
    model.predict.return_value = scores
    with pytest.raises(ValueError, match="invalid score"):
        RerankedRetrieval(retrieval, model=model).retrieve("Play", 6)


def test_tied_scores_preserve_original_order():
    retrieval, model = Mock(), Mock()
    retrieval.retrieve.return_value = [passage("one", 0.8), passage("two", 0.7)]
    model.predict.return_value = [0.1, 0.1]
    result = RerankedRetrieval(retrieval, model=model).retrieve("Play", 6)
    assert [p.passage_id for p in result] == ["one", "two"]


def test_candidate_override_keeps_one_age_filtered_query():
    client = Mock()
    client.query_points.return_value = SimpleNamespace(points=[])
    RetrievalService(client=client).retrieve("Play", 6, limit=20, candidate_limit=20, child_age_days=183)
    assert client.query_points.call_count == 1
    assert client.query_points.call_args.kwargs["limit"] == 20
    assert client.query_points.call_args.kwargs["query_filter"] is not None


@pytest.mark.parametrize("limit", [0, -1, True, 3, 4.5])
def test_invalid_candidate_override_fails_before_cloud_call(limit):
    client = Mock()
    with pytest.raises(ValueError, match="candidate_limit"):
        RetrievalService(client=client).retrieve("Play", 6, limit=4, candidate_limit=limit)
    client.query_points.assert_not_called()
