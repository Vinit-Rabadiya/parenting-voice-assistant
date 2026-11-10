"""Offline metric arithmetic, repeat accounting and dataset integrity checks."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import pytest

from scripts.evaluate_speech import (
    evaluate_model, load_manifest, markdown_report, normalize, summarize, word_errors,
)


def write_wav(path, value=0):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(value.to_bytes(2, "little", signed=True) * 16000)
    path.write_bytes(buffer.getvalue())


def manifest_row(**changes):
    return {"id": "spk01_q01", "speaker": "spk01", "noise": "quiet", "wav": "clip.wav",
            "reference": "My baby eats food", "usage_authorized": True,
            "reference_verified": True, **changes}


def save_manifest(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


@pytest.fixture
def manifest(tmp_path):
    write_wav(tmp_path / "clip.wav")
    path = tmp_path / "manifest.jsonl"
    save_manifest(path, [manifest_row()])
    return path


def test_normalization_preserves_negation_numbers_and_local_vocabulary():
    assert normalize("  Don't give 6.5 ml; try UJI! ") == "do not give 6.5 ml try uji"
    assert normalize("Six-month-old") == "six month old"
    assert normalize("I\u2019m worried") == "i am worried"
    assert normalize("6") != normalize("six")
    assert word_errors("Baby is not feeding", "baby is feeding")["deletions"] == 1


def test_known_substitution_deletion_and_insertion_counts():
    result = word_errors("my baby eats food", "the baby eats")
    assert result == {"reference_words": 4, "substitutions": 1, "deletions": 1, "insertions": 0, "wer": 0.5}
    assert word_errors("baby", "baby eats food")["wer"] == 2
    assert word_errors("my baby", "")["wer"] == 1
    with pytest.raises(ValueError, match="spoken words"):
        word_errors("!!!", "baby")


def test_manifest_uses_real_audio_and_its_fingerprint(manifest):
    rows = load_manifest(manifest)
    assert rows[0]["audio_seconds"] == 1
    assert len(rows[0]["audio_sha256"]) == 64
    assert rows[0]["audio_path"] == manifest.parent / "clip.wav"


@pytest.mark.parametrize("change", [
    {"usage_authorized": False}, {"usage_authorized": "yes"},
    {"reference_verified": False}, {"noise": "perfect"},
    {"speaker": "My private name"}, {"reference": ""},
    {"wav": "../elsewhere.wav"}, {"wav": "missing.wav"},
])
def test_invalid_collection_records_fail_before_inference(manifest, change):
    save_manifest(manifest, [manifest_row(**change)])
    with pytest.raises(ValueError):
        load_manifest(manifest)


def test_smoke_references_do_not_become_verified_study_references(manifest):
    save_manifest(manifest, [manifest_row(reference_verified=False)])
    assert load_manifest(manifest, dataset_kind="smoke")
    with pytest.raises(ValueError, match="verify"):
        load_manifest(manifest, dataset_kind="caregiver")


@pytest.mark.parametrize("duplicate", ["id", "audio"])
def test_duplicate_ids_or_audio_cannot_inflate_sample_size(manifest, duplicate):
    second = manifest_row(id="spk02_q01" if duplicate == "audio" else "spk01_q01")
    save_manifest(manifest, [manifest_row(), second])
    with pytest.raises(ValueError, match="Duplicate"):
        load_manifest(manifest)


def test_invalid_wav_is_not_silently_skipped(manifest):
    (manifest.parent / "clip.wav").write_bytes(b"bad audio")
    with pytest.raises(ValueError):
        load_manifest(manifest)


def test_repeated_trials_do_not_inflate_unique_clip_accuracy(manifest):
    rows = load_manifest(manifest)
    rows[0]["reference"] = "one two three"
    second = {**rows[0], "id": "spk02_q01", "speaker": "spk02", "reference": "hello", "noise": "background"}
    outputs = [("warm up", 0.5), ("one two", 1), ("one two three", 2), ("hello world", 3), ("hello world", 4)]
    service = Mock()
    service.transcribe.side_effect = [SimpleNamespace(text=text, processing_seconds=seconds) for text, seconds in outputs]
    result = evaluate_model([rows[0], second], "base", service, repeats=2)
    summary = result["summary"]
    assert summary["clips"] == 2 and summary["reference_words"] == 4
    assert summary["wer"] == 0.5 and summary["measured_trials"] == 4
    assert summary["processing_seconds_p50"] == 2.5
    assert summary["processing_seconds_p95"] == pytest.approx(3.85)
    assert summary["aggregate_real_time_factor"] == 2.5
    assert summary["unstable_clips"] == 1
    assert result["warmup_processing_seconds"] == 0.5
    assert all(call.kwargs == {"language": "en"} for call in service.transcribe.call_args_list)


def test_retrieval_delta_records_fixed_age_and_missing_baseline(manifest):
    rows = load_manifest(manifest)
    service = Mock()
    service.transcribe.return_value = SimpleNamespace(text="My baby eats", processing_seconds=0.2)
    retrieval = Mock()
    retrieval.retrieve.side_effect = [[SimpleNamespace(passage_id="reference")], [SimpleNamespace(passage_id="different")]]
    age = {"completed_months": 6, "child_age_days": 184}
    result = evaluate_model(rows, "base", service, retriever=retrieval, age=age)
    assert result["retrieval_summary"]["top1_change_rate"] == 1
    assert retrieval.retrieve.call_args.kwargs == {"child_age_days": 184}
    assert retrieval.retrieve.call_args.args[1:] == (6, None, 3)
    retrieval.retrieve.side_effect = [[], []]
    result = evaluate_model(rows, "base", service, retriever=retrieval, age=age)
    assert result["retrieval_summary"]["top1_change_rate"] is None
    assert result["retrieval_summary"]["reference_empty_clips"] == 1


def test_retrieval_outage_does_not_become_a_zero_change_result(manifest):
    service = Mock()
    service.transcribe.return_value = SimpleNamespace(text="My baby eats", processing_seconds=0.2)
    retrieval = Mock()
    retrieval.retrieve.side_effect = RuntimeError("offline")
    with pytest.raises(RuntimeError):
        evaluate_model(load_manifest(manifest), "base", service, retriever=retrieval,
                       age={"completed_months": 6, "child_age_days": 184})


def test_pooled_wer_is_weighted_by_reference_words():
    cases = [{"speaker": "spk01", "audio_seconds": 1, "hypothesis": "one", "trials": [{"text": "one", "processing_seconds": 0.5}],
              "errors": {"reference_words": 10, "substitutions": 1, "deletions": 0, "insertions": 0}},
             {"speaker": "spk02", "audio_seconds": 1, "hypothesis": "two", "trials": [{"text": "two", "processing_seconds": 0.5}],
              "errors": {"reference_words": 1, "substitutions": 0, "deletions": 0, "insertions": 0}}]
    assert summarize(cases)["wer"] == pytest.approx(1 / 11)


def test_document_report_labels_unmeasured_retrieval_and_smoke_scope(manifest):
    service = Mock()
    service.transcribe.return_value = SimpleNamespace(text="My baby eats food", processing_seconds=0.2)
    model = evaluate_model(load_manifest(manifest), "base", service)
    text = markdown_report({"dataset_label": "Generic fixture", "dataset_kind": "smoke", "generated_at": "test",
                            "clip_count": 1, "speaker_count": 1, "models": [model], "limitations": ["Not a Kenyan benchmark."]})
    assert "Not measured" in text and "smoke test" in text
    assert "does not measure Kenyan" in text
    assert "My baby eats food" not in text  # Detailed transcripts stay in the local JSON.


def test_existing_result_directory_is_rejected_before_loading_models(monkeypatch, tmp_path):
    from scripts.evaluate_speech import main
    monkeypatch.setattr("sys.argv", ["evaluate_speech", "missing.jsonl", "--dataset-label", "test", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_manifest_template_is_parseable_but_has_no_claimed_recordings():
    template = Path(__file__).resolve().parents[1] / "eval/stt/manifest.template.jsonl"
    rows = [json.loads(line) for line in template.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 40 and len({row["speaker"] for row in rows}) == 5
    assert all(row["usage_authorized"] is False and row["reference_verified"] is False for row in rows)
