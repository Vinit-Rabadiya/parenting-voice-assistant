from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from firebase_admin import firestore

from backend.services.token_usage import TokenUsageService


def test_persists_overall_totals_across_instances_and_separates_environments(monkeypatch):
    client = Mock()
    records = {}

    def collection(name):
        return SimpleNamespace(document=lambda identifier: SimpleNamespace(path=f"{name}/{identifier}"))

    def create_batch():
        writes = []

        def commit(*, retry, timeout):
            assert retry is None and timeout == 5
            for path, changes in writes:
                data = records.setdefault(path, {})
                for field, transform in changes.items():
                    if isinstance(transform, firestore.Increment):
                        data[field] = data.get(field, 0) + transform.value
                    else:
                        assert isinstance(transform, firestore.Minimum)
                        data[field] = min(data.get(field, transform.value), transform.value)

        def set_document(document, changes, *, merge):
            assert merge
            writes.append((document.path, changes))

        return SimpleNamespace(set=set_document, commit=commit)

    def get_all(references, *, field_paths, retry, timeout):
        for reference in reversed(references):
            data = records.get(reference.path)
            yield SimpleNamespace(reference=reference, exists=data is not None,
                                  to_dict=lambda data=data: {key: data[key] for key in field_paths if key in data})

    client.collection.side_effect = collection
    client.batch.side_effect = create_batch
    client.get_all.side_effect = get_all
    first = TokenUsageService(lambda: client, "production")
    first.flush()
    client.batch.assert_not_called()
    monkeypatch.setattr("backend.services.token_usage.time.time", lambda: 1000)
    first.record("gemini", input_tokens=100, output_tokens=20, thinking_tokens=80, total_tokens=204)
    first.record("gemini", input_tokens=10, output_tokens=5, thinking_tokens=None, total_tokens=None)
    first.record("gemini", input_tokens=None, output_tokens=None, thinking_tokens=None, total_tokens=None)
    client.batch.assert_not_called()
    first.close()

    monkeypatch.setattr("backend.services.token_usage.time.time", lambda: 2000)
    second = TokenUsageService(lambda: client, "production")
    second.record("gemini", input_tokens=8, output_tokens=2, thinking_tokens=None, total_tokens=10)
    second.record("groq", input_tokens=30, output_tokens=10, thinking_tokens=None, total_tokens=40)
    second.flush()
    summary = second.summary()
    assert summary.first_recorded_at == datetime.fromtimestamp(1000, timezone.utc)
    assert [row.total_tokens for row in summary.providers] == [229, 40]
    assert summary.total.model_dump() == {"input_tokens": 148, "output_tokens": 37, "thinking_tokens": 80,
                                          "total_tokens": 269, "model_calls": 4}
    assert TokenUsageService(lambda: client, "development").summary().total.total_tokens == 0
    assert set(records) == {"model_token_usage/production-gemini", "model_token_usage/production-groq"}
