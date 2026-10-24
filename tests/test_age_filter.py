from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.services.retrieval import RetrievalService, build_age_filter, is_age_eligible
from scripts.create_qdrant_collection import ensure_age_indexes
from scripts import create_qdrant_collection


@pytest.fixture
def age_collection():
    # Real local Qdrant filtering, without network calls or embedding inference.
    client = QdrantClient(":memory:")
    client.create_collection("ages", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    bands = [
        {"min_days": 0, "max_days_exclusive": 7},
        {"min_days": 7, "max_months_exclusive": 6},
        {"min_months": 6, "max_months_exclusive": 9},
        {"min_months": 9, "max_months_exclusive": 12},
        {"min_months": 24, "max_months_exclusive": None},
        {"min_days": 0, "max_days_exclusive": None},
        {},
        {"min_months": 0},  # Missing is not an explicitly null upper bound.
    ]
    client.upsert("ages", points=[
        PointStruct(id=i, vector=[1.0, 0.0], payload={"source_age": band})
        for i, band in enumerate(bands)
    ])
    yield client, bands
    client.close()


@pytest.mark.parametrize("months,days", [
    (0, 0), (0, 6), (0, 7), (5, 180), (6, 181), (6, 184),
    (8, 273), (9, 274), (24, 730), (0.1, None),
])
def test_qdrant_filter_matches_python_age_policy(age_collection, months, days):
    client, bands = age_collection
    points = client.query_points(
        "ages", query=[1.0, 0.0], limit=100,
        query_filter=build_age_filter(months, child_age_days=days),
    ).points
    expected = {
        i for i, band in enumerate(bands)
        if is_age_eligible(band, months, child_age_days=days)
    }
    assert {point.id for point in points} == expected


def test_age_filter_finds_eligible_passage_beyond_unfiltered_candidate_limit():
    client = QdrantClient(":memory:")
    try:
        client.create_collection("ages", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert("ages", points=[
            PointStruct(id=i, vector=[1.0, 0.0], payload={
                "source_age": {"min_months": 12, "max_months_exclusive": 24},
            }) for i in range(20)
        ] + [PointStruct(id=20, vector=[0.8, 0.2], payload={
            "source_age": {"min_months": 6, "max_months_exclusive": 9},
        })])
        assert 20 not in {p.id for p in client.query_points("ages", query=[1.0, 0.0], limit=15).points}
        result = client.query_points(
            "ages", query=[1.0, 0.0], limit=15,
            query_filter=build_age_filter(6, child_age_days=181),
        )
        assert [p.id for p in result.points] == [20]
    finally:
        client.close()


def test_retrieval_passes_age_filter_to_qdrant():
    client = MagicMock()
    client.query_points.return_value.points = []
    RetrievalService(client=client).retrieve("play", 6, child_age_days=181)
    assert client.query_points.call_args.kwargs["query_filter"] == build_age_filter(6, child_age_days=181)


def test_retrieval_without_age_does_not_apply_age_filter():
    client = MagicMock()
    client.query_points.return_value.points = []
    RetrievalService(client=client).retrieve("play")
    assert client.query_points.call_args.kwargs["query_filter"] is None


@pytest.mark.parametrize("months,days", [(True, None), (-1, None), (float("nan"), None), (6, True), (6, -1)])
def test_invalid_age_fails_before_qdrant_request(months, days):
    client = MagicMock()
    with pytest.raises(ValueError):
        RetrievalService(client=client).retrieve("play", months, child_age_days=days)
    client.query_points.assert_not_called()


def test_age_indexes_cover_all_filter_fields():
    client = MagicMock()
    ensure_age_indexes(client, "ages")
    calls = client.create_payload_index.call_args_list
    assert {call.kwargs["field_name"] for call in calls} == {
        "source_age.min_days", "source_age.max_days_exclusive",
        "source_age.min_months", "source_age.max_months_exclusive",
    }
    assert len(calls) == 4
    assert all(call.kwargs["collection_name"] == "ages" and call.kwargs["wait"] for call in calls)


def test_setup_adds_indexes_without_recreating_existing_collection(monkeypatch):
    client = MagicMock()
    client.collection_exists.return_value = True
    monkeypatch.setattr(create_qdrant_collection, "QdrantClient", lambda **kwargs: client)
    monkeypatch.setattr(create_qdrant_collection.settings, "QDRANT_URL", "https://example.org")
    monkeypatch.setattr(create_qdrant_collection.settings, "QDRANT_API_KEY", "test-key")
    create_qdrant_collection.main([])
    client.create_collection.assert_not_called()
    assert client.create_payload_index.call_count == 4
    client.close.assert_called_once()
