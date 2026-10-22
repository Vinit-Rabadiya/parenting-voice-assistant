from scripts.prepare_coverage_review import coverage_markdown, prepare_review


def passage():
    return {"passage_id": "p1", "source_id": "source", "source_age": {
        "min_months": 6, "max_months_exclusive": 12}, "routines": ["feeding"],
        "developmental_domain": "nutrition"}


def test_review_does_not_treat_age_eligibility_as_relevance():
    inventory = {"evaluation_date": "2026-10-22", "cases": [
        {"id": "q1", "date_of_birth": "2026-04-22", "query": "Feeding ideas"},
        {"id": "q2", "date_of_birth": "2026-08-22", "query": "Feeding ideas"}]}
    cases = prepare_review([passage()], inventory)
    assert cases[0]["age_eligible_passage_ids"] == ["p1"]
    assert cases[1]["age_eligible_passage_ids"] == []
    assert all(case["expected_passage_ids"] is None for case in cases)
    assert all(case["review_status"] == "pending" for case in cases)


def test_out_of_scope_case_is_not_sent_through_retrieval_age_validation():
    inventory = {"evaluation_date": "2026-10-22", "cases": [
        {"id": "q1", "date_of_birth": "2024-10-21", "category": "out_of_scope", "query": "Play"}]}
    case = prepare_review([passage()], inventory)[0]
    assert case["age_context"] is None
    assert case["age_eligible_passage_ids"] == []


def test_coverage_includes_missing_routines_without_claiming_accuracy():
    report = coverage_markdown([passage()])
    assert "| 6 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |" in report
    assert "not semantic relevance" in report
    assert "not classified" not in report
