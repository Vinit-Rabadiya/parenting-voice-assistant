from unittest.mock import MagicMock

import pytest

import conftest


@pytest.mark.parametrize("required,present", [(False, False), (False, True), (True, True)])
def test_corpus_requirement_allows_optional_or_present_file(tmp_path, monkeypatch, required, present):
    path = tmp_path / "passages.jsonl"
    if present:
        path.touch()
    monkeypatch.setattr(conftest, "CORPUS_PATH", path)
    session = MagicMock()
    session.config.getoption.return_value = required
    conftest.pytest_sessionstart(session)


def test_required_missing_corpus_fails_with_preparation_instructions(tmp_path, monkeypatch):
    monkeypatch.setattr(conftest, "CORPUS_PATH", tmp_path / "missing.jsonl")
    session = MagicMock()
    session.config.getoption.return_value = True
    with pytest.raises(pytest.UsageError, match="scripts.build_rag_passages"):
        conftest.pytest_sessionstart(session)
