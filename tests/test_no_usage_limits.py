"""Application quotas and account usage routes are removed."""
from unittest.mock import Mock

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.services.coaching import CoachingResult


def test_coaching_has_no_hourly_request_limit_or_usage_storage_dependency(client, monkeypatch):
    data, retrieval, coaching = Mock(), Mock(), Mock()
    data.get_child.return_value = {"age_months": 6, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.create_interaction.return_value = "interaction-1"
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult("Talk gently with your baby.", [], answer_basis="general_information")
    for dependency, provider in ((require_authenticated_user, lambda: {"uid": "account"}),
                                  (get_caregiver_data_service, lambda: data),
                                  (get_retrieval_service, lambda: retrieval), (get_coaching_service, lambda: coaching)):
        monkeypatch.setitem(client.app.dependency_overrides, dependency, provider)
    for _ in range(35):
        response = client.post("/coach", json={"child_id": "child", "question": "How can I encourage babbling?"})
        assert response.status_code == 200
    assert not data.client.mock_calls
    assert coaching.generate.call_count == 35
    for path in ("/me/usage", "/api/v1/me/usage"):
        assert client.get(path).status_code == 404
