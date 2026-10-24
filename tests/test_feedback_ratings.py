from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.schemas.coaching import FeedbackRecord, FeedbackRequest
from backend.services.caregiver_data import CaregiverDataService


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_numeric_feedback_is_not_converted_to_a_boolean(rating):
    feedback = FeedbackRequest(rating=rating, reasons=["unclear"])
    assert feedback.helpful is None
    stored = CaregiverDataService._feedback_data(None, " Clear ", rating=rating, reasons=feedback.reasons)
    assert stored["rating"] == rating
    assert stored["helpful"] is None
    assert stored["comment"] == "Clear"
    assert "review_status" not in stored


@pytest.mark.parametrize("value", [0, 6, True, 3.5, "4"])
def test_invalid_numeric_ratings_are_rejected(value):
    with pytest.raises(ValidationError):
        FeedbackRequest(rating=value)


@pytest.mark.parametrize("payload", [{}, {"reasons": ["unclear"]},
                                     {"rating": 2, "reasons": ["unknown"]},
                                     {"rating": 2, "reasons": ["unclear", "unclear"]}])
def test_feedback_requires_a_value_and_valid_unique_reasons(payload):
    with pytest.raises(ValidationError):
        FeedbackRequest(**payload)


def test_historical_boolean_feedback_has_no_invented_numeric_rating():
    record = FeedbackRecord(helpful=False, recorded_at=datetime.now(timezone.utc))
    assert record.helpful is False
    assert record.rating is None


def test_replacement_feedback_does_not_create_private_review_metadata():
    stored = CaregiverDataService._feedback_data(None, None, rating=5)
    assert "review_status" not in stored
    assert stored["reasons"] == []
