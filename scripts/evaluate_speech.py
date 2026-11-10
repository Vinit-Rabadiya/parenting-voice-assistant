"""Measure the unchanged English speech service against local reference recordings."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import time
import unicodedata

import jiwer

from backend.services.audio_validation import validate_audio
from backend.services.speech_errors import InvalidAudioError


ROOT = Path(__file__).resolve().parents[1]
NORMALIZATION = (
    "NFKC and lowercase; curly apostrophes standardized; common English contractions expanded; "
    "punctuation replaced by spaces except decimal points inside numbers; whitespace collapsed. "
    "Numbers, negation and local vocabulary are not corrected or substituted."
)


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower().replace("\u2019", "'")
    text = jiwer.ExpandCommonEnglishContractions()(text)
    cleaned = []
    for i, char in enumerate(text):
        decimal = (char == "." and 0 < i < len(text) - 1
                   and text[i - 1].isdigit() and text[i + 1].isdigit())
        cleaned.append(char if char.isalnum() or char.isspace() or decimal else " ")
    return " ".join("".join(cleaned).split())


def word_errors(reference, hypothesis):
    reference = normalize(reference)
    if not reference:
        raise ValueError("A reference must contain spoken words.")
    result = jiwer.process_words(reference, normalize(hypothesis))
    return {"reference_words": result.hits + result.substitutions + result.deletions,
            "substitutions": result.substitutions, "deletions": result.deletions,
            "insertions": result.insertions, "wer": result.wer}


def load_manifest(path, *, audio_root=None, dataset_kind="caregiver"):
    """Validate all files before model loading; keep participant names out of IDs."""
    base = (audio_root or path.parent).resolve()
    rows, identifiers, fingerprints = [], set(), set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Manifest line {line_number} must be an object.")
        for field in ("id", "speaker", "noise", "wav", "reference"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Manifest line {line_number} needs {field}.")
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row[field]) for field in ("id", "speaker")):
            raise ValueError("Use short pseudonymous case and speaker IDs.")
        if row["noise"] not in {"quiet", "background", "unknown"}:
            raise ValueError("Noise must be quiet, background or unknown.")
        if row.get("usage_authorized") is not True:
            raise ValueError(f"{row['id']}: confirm permission to use this recording before evaluation.")
        if dataset_kind != "smoke" and row.get("reference_verified") is not True:
            raise ValueError(f"{row['id']}: listen and verify the reference transcript before evaluation.")
        if row["id"] in identifiers:
            raise ValueError("Duplicate speech case ID.")
        relative = Path(row["wav"])
        audio_path = (base / relative).resolve()
        if relative.is_absolute() or not audio_path.is_relative_to(base):
            raise ValueError("WAV paths must remain under the audio root.")
        if not audio_path.is_file():
            raise ValueError(f"{row['id']}: WAV file is missing.")
        if audio_path.stat().st_size > 16000 * 2 * 30 + 4096:
            raise ValueError(f"{row['id']}: WAV file exceeds the application limit.")
        audio = audio_path.read_bytes()
        try:
            duration = validate_audio(audio)
        except InvalidAudioError as exc:
            raise ValueError(f"{row['id']}: {exc}") from None
        fingerprint = hashlib.sha256(audio).hexdigest()
        if fingerprint in fingerprints:
            raise ValueError("Duplicate audio bytes cannot count as independent recordings.")
        word_errors(row["reference"], "")
        identifiers.add(row["id"])
        fingerprints.add(fingerprint)
        rows.append({**row, "audio_path": audio_path, "audio_seconds": duration,
                     "audio_sha256": fingerprint})
    if not rows:
        raise ValueError("The manifest contains no recordings.")
    return rows


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def summarize(cases):
    counts = {key: sum(case["errors"][key] for case in cases)
              for key in ("reference_words", "substitutions", "deletions", "insertions")}
    trials = [trial for case in cases for trial in case["trials"]]
    seconds = [trial["processing_seconds"] for trial in trials]
    audio = sum(case["audio_seconds"] * len(case["trials"]) for case in cases)
    return {
        "clips": len(cases), "speakers": len({case["speaker"] for case in cases}), **counts,
        "wer": (counts["substitutions"] + counts["deletions"] + counts["insertions"]) / counts["reference_words"],
        "audio_seconds": sum(case["audio_seconds"] for case in cases),
        "measured_trials": len(trials),
        "processing_seconds_p50": statistics.median(seconds),
        "processing_seconds_p95": percentile(seconds, 0.95),
        "aggregate_real_time_factor": sum(seconds) / audio,
        "unstable_clips": sum(any(normalize(trial["text"]) != normalize(case["hypothesis"])
                                  for trial in case["trials"]) for case in cases),
    }


def evaluate_model(rows, model, service, *, repeats=1, retriever=None, age=None):
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("Repeats must be from 1 to 10.")
    # Warm the encoder and decoder on one actual clip. This call is excluded
    # from accuracy and warm latency; its time is recorded separately.
    warmup = service.transcribe(rows[0]["audio_path"].read_bytes(), language="en")
    cases = []
    for row in rows:
        audio = row["audio_path"].read_bytes()
        if hashlib.sha256(audio).hexdigest() != row["audio_sha256"]:
            raise ValueError(f"{row['id']}: audio changed after validation; restart the run.")
        trials = []
        for _ in range(repeats):
            started = time.perf_counter()
            result = service.transcribe(audio, language="en")
            wall = time.perf_counter() - started
            if (not isinstance(result.text, str) or not math.isfinite(result.processing_seconds)
                    or result.processing_seconds < 0):
                raise ValueError("The speech service returned invalid benchmark data.")
            trials.append({"text": result.text, "processing_seconds": result.processing_seconds,
                           "service_wall_seconds": wall})
        hypothesis = trials[0]["text"]
        case = {key: row[key] for key in ("id", "speaker", "noise", "audio_seconds", "audio_sha256")}
        case.update(reference=row["reference"], hypothesis=hypothesis, trials=trials,
                    errors=word_errors(row["reference"], hypothesis))
        if retriever is not None:
            def retrieve(text):
                return [item.passage_id for item in retriever.retrieve(
                    text, age["completed_months"], None, 3, child_age_days=age["child_age_days"],
                )]
            reference_ids, hypothesis_ids = retrieve(row["reference"]), retrieve(hypothesis)
            reference_top = reference_ids[0] if reference_ids else None
            hypothesis_top = hypothesis_ids[0] if hypothesis_ids else None
            case["retrieval"] = {"reference_ids": reference_ids, "hypothesis_ids": hypothesis_ids,
                                 "reference_has_match": reference_top is not None,
                                 "top1_changed": reference_top != hypothesis_top}
        cases.append(case)
    report = {"model": model, "warmup_processing_seconds": warmup.processing_seconds,
              "summary": summarize(cases), "cases": cases}
    for dimension in ("speaker", "noise"):
        report[f"by_{dimension}"] = {
            label: summarize([case for case in cases if case[dimension] == label])
            for label in sorted({case[dimension] for case in cases})
        }
    if retriever is not None:
        eligible = [case for case in cases if case["retrieval"]["reference_has_match"]]
        changed = sum(case["retrieval"]["top1_changed"] for case in eligible)
        report["retrieval_summary"] = {
            "reference_matched_clips": len(eligible), "top1_changed": changed,
            "top1_change_rate": changed / len(eligible) if eligible else None,
            "reference_empty_clips": len(cases) - len(eligible),
            "scope": "Raw top-one retrieval at one fixed age; not a correctness or answer-quality metric.",
        }
    return report


def markdown_report(report):
    def percent(value):
        return f"{value * 100:.2f}%" if value is not None else "Not measured"
    try:
        generated = datetime.fromisoformat(report["generated_at"]).astimezone(timezone(timedelta(hours=3))).strftime("%d %B %Y, %H:%M EAT")
    except ValueError:
        generated = report["generated_at"]
    lines = ["# English speech evaluation", "", f"Dataset: **{report['dataset_label']}**.",
             f"Run type: **{report['dataset_kind']}**. Generated {generated}.", "",
             f"Unique recordings: {report['clip_count']}. Speaker IDs: {report['speaker_count']}.",
             f"References marked verified: {report.get('reference_verified_clips', 0)} of {report['clip_count']}.",
             "", "| Model | WER | Median transcription (s) | P95 (s) | Real-time factor | Top-one retrieval change |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for model in report["models"]:
        summary = model["summary"]
        change = model.get("retrieval_summary", {}).get("top1_change_rate")
        lines.append(f"| {model['model']} | {percent(summary['wer'])} | {summary['processing_seconds_p50']:.3f} | "
                     f"{summary['processing_seconds_p95']:.3f} | {summary['aggregate_real_time_factor']:.3f} | {percent(change)} |")
    lines += ["", "## Method", "",
              "The pretrained models were evaluated without retraining, using the application's English-only "
              "SpeechService on CPU with INT8. The JSON report records package versions, model snapshots, "
              "source-code and audio fingerprints, and all case outcomes.", "",
              "WER = (substitutions + deletions + insertions) / reference words. The pooled WER uses "
              "the first measured transcript of each unique clip. Repeats contribute to latency and stability "
              "measurements, not additional independent accuracy samples. WER can exceed 100%.", "",
              f"Normalization: {NORMALIZATION}", "",
              "The first actual transcription per model is a warm-up, excluded from the table. Model loading "
              "and warm-up times are recorded separately. Real-time factor divides total measured transcription "
              "time by the duration of the recordings processed in those trials; below 1 means faster than the "
              "recorded audio. These are transcription measurements, excluding upload, authentication, "
              "retrieval, generation, database writes and spoken playback.", "",
              "## Model loading and execution environment", "",
              "| Model | Snapshot | Model load (s) | Warm-up transcription (s) |",
              "| --- | --- | ---: | ---: |"]
    for model in report["models"]:
        lines.append(f"| {model['model']} | {model.get('model_snapshot', 'Not recorded')} | "
                     f"{model.get('model_load_seconds', 0):.3f} | {model['warmup_processing_seconds']:.3f} |")
    environment = report.get("provenance", {})
    packages = ", ".join(f"{key} {value}" for key, value in environment.get("packages", {}).items())
    lines += ["", f"Platform: {environment.get('platform', 'Not recorded')}. "
              f"Processor descriptor: {environment.get('processor', 'Not recorded')}. "
              f"CPU threads: {environment.get('cpu_threads', 'Not recorded')}. "
              f"Python: {environment.get('python', 'Not recorded')}.", "",
              f"Packages: {packages or 'Not recorded'}.", "",
              "## Speaker and recording-condition results", "",
              "| Model | Group | Label | Clips | WER | Median transcription (s) |",
              "| --- | --- | --- | ---: | ---: | ---: |"]
    for model in report["models"]:
        for dimension in ("speaker", "noise"):
            for label, summary in model[f"by_{dimension}"].items():
                lines.append(f"| {model['model']} | {dimension} | {label} | {summary['clips']} | "
                             f"{percent(summary['wer'])} | {summary['processing_seconds_p50']:.3f} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    if report["dataset_kind"] == "smoke":
        lines += ["", "**This smoke test checks the evaluation implementation. It does not measure Kenyan "
                  "caregiver speech recognition or establish model suitability.**"]
    lines += ["", "Detailed transcripts remain in the accompanying local JSON report. Review them before sharing.", ""]
    return "\n".join(lines)


def provenance():
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    return {"code_revision": git("rev-parse", "HEAD"), "working_tree_dirty": bool(git("status", "--porcelain")),
            "speech_service_sha256": hashlib.sha256((ROOT / "backend/services/speech.py").read_bytes()).hexdigest(),
            "evaluation_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "platform": platform.platform(), "processor": platform.processor(), "python": platform.python_version(),
            "cpu_threads": min(4, os.cpu_count() or 1),
            "packages": {name: version(name) for name in ("faster-whisper", "ctranslate2", "jiwer")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audio-root", type=Path, help="Defaults to the manifest directory.")
    parser.add_argument("--models", nargs="+", choices=("tiny.en", "base", "small"), default=["base"])
    parser.add_argument("--repeats", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--dataset-kind", choices=("smoke", "caregiver", "public"), default="caregiver")
    parser.add_argument("--dataset-label", required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="A new directory; existing results are never overwritten.")
    parser.add_argument("--allow-model-download", action="store_true", help="Opt in to downloading missing model files.")
    parser.add_argument("--retrieval", action="store_true", help="Send reference and hypothesis text to configured Qdrant Cloud.")
    parser.add_argument("--date-of-birth")
    parser.add_argument("--evaluation-date")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory already exists. Choose a new run directory.")
    if len(set(args.models)) != len(args.models):
        parser.error("Do not repeat a model name.")
    retriever, age = None, None
    try:
        rows = load_manifest(args.manifest, audio_root=args.audio_root, dataset_kind=args.dataset_kind)
        if args.retrieval:
            from scripts.evaluate_retrieval import query_age_context
            from backend.services.retrieval import RetrievalService
            age = query_age_context({"date_of_birth": args.date_of_birth, "evaluation_date": args.evaluation_date})
            retriever = RetrievalService(cache_ttl_seconds=0)
        from faster_whisper.utils import download_model
        from backend.services.speech import SpeechService
        # Resolve every model before starting inference, with downloads disabled by default.
        paths = {model: download_model(model, local_files_only=not args.allow_model_download) for model in args.models}
        report = {
            "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_kind": args.dataset_kind, "dataset_label": args.dataset_label,
            "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "clip_count": len(rows), "speaker_count": len({row["speaker"] for row in rows}),
            "reference_verified_clips": sum(row.get("reference_verified") is True for row in rows),
            "noise_counts": dict(Counter(row["noise"] for row in rows)),
            "normalization": NORMALIZATION, "repeats": args.repeats, "provenance": provenance(),
            "speech_settings": {"language": "en", "device": "cpu", "compute_type": "int8",
                                "beam_size": 3, "temperature": 0.0, "best_of": 1,
                                "condition_on_previous_text": False, "vad_filter": True,
                                "cpu_threads": min(4, os.cpu_count() or 1), "num_workers": 1},
            "retrieval": {"enabled": args.retrieval, "age": age,
                          "collection": retriever.collection_name if retriever else None,
                          "corpus_revision": retriever.corpus_revision if retriever else None},
            "models": [],
            "limitations": [
                "This sample is not a population estimate or clinical validation.",
                "Timing depends on this machine, recording length, noise and model-cache state; it is not hosted end-to-end latency.",
                "Case, punctuation and contraction normalization does not establish semantic accuracy; review age and negation errors separately.",
                "No statistical confidence interval or independent reference-transcript review is implied by this report.",
                "Model order is fixed and warm-up uses the first clip; repeat on the target host before changing the production model.",
                "With few measured trials, P95 is descriptive rather than a reliable tail-latency estimate.",
                "Retrieval change is measured only when explicitly enabled; it does not measure downstream answer correctness.",
            ],
        }
        for model, path in paths.items():
            started = time.perf_counter()
            service = SpeechService(path)
            load_seconds = time.perf_counter() - started
            result = evaluate_model(rows, model, service, repeats=args.repeats, retriever=retriever, age=age)
            result.update(model_snapshot=Path(path).name, model_load_seconds=load_seconds)
            report["models"].append(result)
            del service
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "report.md").write_text(markdown_report(report), encoding="utf-8")
    except Exception as exc:
        # Avoid provider exception descriptions that may contain submitted text.
        if isinstance(exc, (ValueError, FileNotFoundError)):
            parser.error(str(exc))
        parser.exit(1, f"Evaluation failed ({type(exc).__name__}). No completed report was produced.\n")
    finally:
        if retriever is not None:
            retriever.close()
    print(f"Saved {args.output_dir / 'report.md'} and report.json ({args.dataset_kind}; {len(rows)} clips).")


if __name__ == "__main__":
    main()
