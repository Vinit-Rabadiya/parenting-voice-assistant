"""Age-policy integration checks using prepared passages and local Qdrant.

The constant vectors deliberately test filtering, not embedding quality or ranking.
Firebase, generation, and persistence are isolated; no cloud data is read or written.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.config import PROJECT_ROOT, settings
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services import caregiver_data
from backend.services.age import add_months, age_details
from backend.services.coaching import CoachingResult
from backend.services.retrieval import RetrievalService, build_age_filter
from scripts.index_rag import load_passages, validate_source_references


TODAY = date(2026, 10, 20)
BOUNDARIES = [
    pytest.param(date(2026, 10, 14), id="six-days"),
    pytest.param(date(2026, 10, 13), id="seven-days"),
    pytest.param(date(2026, 4, 21), id="day-before-six-months"),
    pytest.param(date(2026, 4, 20), id="exactly-six-months"),
    pytest.param(date(2024, 10, 20), id="second-birthday"),
]


def eligible_on_date(source_age, birth_date):
    # Independent oracle: compare calendar dates, not the production age predicate.
    if "min_days" in source_age:
        start = birth_date + timedelta(days=source_age["min_days"])
    else:
        start = add_months(birth_date, source_age["min_months"])
    if "max_days_exclusive" in source_age:
        upper = source_age["max_days_exclusive"]
        end = None if upper is None else birth_date + timedelta(days=upper)
    else:
        upper = source_age["max_months_exclusive"]
        end = None if upper is None else add_months(birth_date, upper)
    return start <= TODAY and (end is None or TODAY < end)


@pytest.fixture(scope="module")
def corpus_collection():
    path = PROJECT_ROOT / "data/processed/rag/passages.jsonl"
    if not path.exists():
        pytest.skip("Prepare the real corpus with python -m scripts.build_rag_passages first.")
    passages = load_passages(path)
    validate_source_references(passages, PROJECT_ROOT / "data/sources.json")
    client = QdrantClient(":memory:")
    try:
        client.create_collection("corpus", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert("corpus", points=[
            PointStruct(id=i, vector=[1.0, 0.0], payload=passage)
            for i, passage in enumerate(passages)
        ])
        yield client, passages
    finally:
        client.close()


class LocalVectorClient:
    """Replace only cloud embedding inference; execute the actual Qdrant filter."""

    def __init__(self, client):
        self.client = client
        self.calls = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs.copy())
        return self.client.query_points(**{**kwargs, "query": [1.0, 0.0]})


@pytest.mark.parametrize("birth_date", BOUNDARIES)
def test_real_corpus_filter_and_retrieval_match_calendar_boundaries(corpus_collection, birth_date):
    client, passages = corpus_collection
    days, months, _ = age_details(birth_date, TODAY)
    expected = {p["passage_id"] for p in passages if eligible_on_date(p["source_age"], birth_date)}
    assert expected, "A boundary check must not pass with no eligible reference passages."

    # Request the entire corpus so this asserts both no age leaks and no omissions.
    points = client.query_points(
        "corpus", query=[1.0, 0.0], limit=len(passages),
        query_filter=build_age_filter(months, child_age_days=days),
    ).points
    assert {p.payload["passage_id"] for p in points} == expected
    adapter = LocalVectorClient(client)
    results = RetrievalService(client=adapter, collection_name="corpus").retrieve(
        "How can I support learning through play?", months,
        child_age_days=days, limit=len(passages),
    )
    assert {p.passage_id for p in results} == expected


@pytest.fixture
def corpus_api(corpus_collection, monkeypatch):
    local, passages = corpus_collection
    adapter = LocalVectorClient(local)
    retrieval = RetrievalService(client=adapter, collection_name="corpus")
    data, coaching = MagicMock(), MagicMock()
    data.create_interaction.return_value = "local-interaction"
    coaching.generate.side_effect = lambda question, months, routine, evidence: CoachingResult(
        "Local test guidance.", evidence,
        answer_basis="reference_assisted" if evidence else "general_information",
    )
    monkeypatch.setattr(caregiver_data, "current_date", lambda: TODAY)
    monkeypatch.setattr(settings, "RETRIEVAL_MIN_SCORE", 0.50)
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        require_authenticated_user: lambda: {"uid": "local-user"},
        get_caregiver_data_service: lambda: data,
        get_retrieval_service: lambda: retrieval,
        get_coaching_service: lambda: coaching,
    })
    try:
        yield data, coaching, adapter, passages
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


def stored_profile(birth_date):
    document = MagicMock(id="local-child")
    document.to_dict.return_value = {"name": "Local child", "date_of_birth": birth_date.isoformat()}
    return caregiver_data.CaregiverDataService._child_response(document)


@pytest.mark.parametrize("birth_date", BOUNDARIES)
def test_coaching_api_uses_real_corpus_with_server_calculated_age(client, corpus_api, birth_date):
    data, coaching, adapter, passages = corpus_api
    data.get_child.return_value = stored_profile(birth_date)
    response = client.post("/coach", json={
        "child_id": "local-child", "question": "How can I support learning through play?",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    citations = response.json()["citations"]
    assert citations
    expected = {p["passage_id"] for p in passages if eligible_on_date(p["source_age"], birth_date)}
    assert {p["passage_id"] for p in citations} <= expected
    days, months, _ = age_details(birth_date, TODAY)
    assert adapter.calls[-1]["query_filter"] == build_age_filter(months, child_age_days=days)
    coaching.generate.assert_called_once()
    data.create_interaction.assert_called_once()


@pytest.mark.parametrize("birth_date", [
    pytest.param(date(2024, 10, 19), id="day-after-second-birthday"),
    pytest.param(date(2024, 4, 20), id="thirty-months"),
])
def test_coaching_api_declines_older_children_before_corpus_search(client, corpus_api, birth_date):
    data, coaching, adapter, _ = corpus_api
    data.get_child.return_value = stored_profile(birth_date)
    response = client.post("/coach", json={"child_id": "local-child", "question": "Play ideas"})
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["response_kind"] == "age_out_of_scope"
    assert adapter.calls == []
    coaching.generate.assert_not_called()
    data.create_interaction.assert_called_once()
    assert response.json()["citations"] == []
