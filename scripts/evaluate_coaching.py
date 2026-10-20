"""Capture synthetic coaching evaluation cases; preview by default, opt in to live calls."""

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

from backend.core.config import PROJECT_ROOT, settings
from backend.services.age import add_months, age_details, current_date
from backend.services.coaching import CoachingService
from backend.services.evidence import NO_GUIDANCE_MESSAGE, select_evidence
from backend.services.retrieval import RetrievalService
from backend.services.response_safety import SAFE_RESPONSE, inspect_response
from backend.services.input_safety import ESCALATION_MESSAGE, inspect_input
from backend.services.crisis_safety import inspect_crisis


QUESTION_SET_VERSION = "coaching-quality-v1"
QUESTION_SET_PATH = "data/evaluation/coaching-questions.json"
PILOT = ("aq01", "aq10", "aq21", "aq32")


def git_output(*args):
    return subprocess.check_output(
        ["git", *args], cwd=PROJECT_ROOT, text=True, encoding="utf-8",
    ).strip()


def load_cases(path: Path | None = None):
    """Load versioned evaluation data without requiring historical Git objects."""
    data = json.loads((path or PROJECT_ROOT / QUESTION_SET_PATH).read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
            or data.get("question_set_version") != QUESTION_SET_VERSION
            or not isinstance(data.get("cases"), list)):
        raise ValueError("Unsupported coaching question-set format or version.")
    cases = {}
    fields = {"id", "target_months", "routine", "question", "expected_behaviour"}
    for case in data["cases"]:
        if not isinstance(case, dict) or set(case) != fields:
            raise ValueError("Each coaching case must define the required fields.")
        case_id = case["id"]
        if not isinstance(case_id, str) or case_id not in {f"aq{i:02}" for i in range(1, 41)}:
            raise ValueError("Invalid coaching case identifier.")
        if case_id in cases:
            raise ValueError("Duplicate coaching case identifier.")
        if type(case["target_months"]) is not int or case["target_months"] not in (0, 3, 6, 12, 24):
            raise ValueError("Invalid target age in coaching case.")
        if case["routine"] not in (None, "feeding", "bathing", "play", "dressing", "reading"):
            raise ValueError("Invalid routine in coaching case.")
        if any(not isinstance(case[field], str) or not case[field].strip()
               for field in ("question", "expected_behaviour")):
            raise ValueError("Coaching input and expected behaviour must be nonempty text.")
        cases[case_id] = case
    if len(cases) != 40:
        raise ValueError("The approved question set must contain exactly 40 cases.")
    # Hash canonical data, so formatting and Windows/Linux line endings do not alter identity.
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return cases, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def profile_dates(evaluation_date, months):
    birth = add_months(evaluation_date, -months)
    days, completed, fractional = age_details(birth, evaluation_date)
    if completed != months or (months == 24 and add_months(birth, 24) != evaluation_date):
        raise ValueError("Choose another evaluation date to represent the exact target age.")
    return {
        "evaluation_date": evaluation_date.isoformat(), "date_of_birth": birth.isoformat(),
        "age_days": days, "completed_months": completed, "age_months": round(fractional, 1),
    }


class CaptureModels:
    """Observe the actual service call without duplicating its prompt or fallback logic."""

    def __init__(self, models):
        self.models = models
        self.attempts = []

    def generate_content(self, **kwargs):
        attempt = {
            "model": kwargs["model"], "prompt": kwargs["contents"],
            "generation_config": kwargs["config"].model_dump(mode="json", exclude_none=True),
            "outcome": "started",
        }
        self.attempts.append(attempt)
        started = time.perf_counter()
        try:
            response = self.models.generate_content(**kwargs)
            attempt["outcome"] = "completed"
            return response
        except Exception as exc:
            attempt["outcome"] = "error"
            attempt["error_type"] = type(exc).__name__
            code = getattr(exc, "code", None)
            attempt["error_code"] = code if type(code) is int else None
            raise
        finally:
            attempt["seconds"] = round(time.perf_counter() - started, 3)


def capture_case(case, profile, retrieval, coaching):
    record = {
        "case": case, "profile": profile, "outcome": "incomplete",
        "retrieved": [], "supplied_evidence": [], "attempts": [],
        "answer": None, "selected_model": None, "fallback_used": False,
        "timings_seconds": {}, "ratings": None, "audio_playback": "not_checked",
        "limitations": "Direct service evaluation: excludes authentication, Firestore, ASR and TTS.",
    }
    started = time.perf_counter()
    stage = "retrieval"
    observer = None
    try:
        tick = time.perf_counter()
        stage = "input_safety"
        crisis = inspect_crisis(case["question"])
        triage = inspect_input(case["question"], profile["completed_months"])
        record["caregiver_safety"] = {"kind": crisis.kind, "reasons": list(crisis.reasons)}
        record["input_safety"] = {"escalate": triage.escalate, "reasons": list(triage.reasons)}
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        if triage.escalate or crisis.kind:
            record.update(outcome="escalated" if triage.escalate else crisis.kind,
                          answer=ESCALATION_MESSAGE if triage.escalate else crisis.answer,
                          referral_sources=list(triage.citations))
            return record
        stage = "retrieval"
        tick = time.perf_counter()
        passages = retrieval.retrieve(
            case["question"], profile["completed_months"], case["routine"], 3,
            child_age_days=profile["age_days"],
        )
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        record["retrieved"] = [asdict(p) for p in passages]
        stage = "evidence_selection"
        tick = time.perf_counter()
        evidence = select_evidence(passages, settings.RETRIEVAL_MIN_SCORE)
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        record["supplied_evidence"] = [asdict(p) for p in evidence]
        if not evidence:
            record.update(outcome="no_evidence", answer=NO_GUIDANCE_MESSAGE)
            return record
        stage = "generation"
        tick = time.perf_counter()
        observer = CaptureModels(coaching.client.models)
        service = CoachingService(
            model=coaching.model, fallback_model=coaching.fallback_model,
            client=SimpleNamespace(models=observer),
        )
        result = service.generate(case["question"], profile["age_months"], case["routine"], evidence)
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        record.update(outcome="answered", answer=result.answer)
        record["selected_model"] = observer.attempts[-1]["model"]
        stage = "response_safety"
        tick = time.perf_counter()
        decision = inspect_response(result.answer, result.passages, evidence, profile["age_months"])
        record["safety"] = {"blocked": decision.blocked, "reasons": list(decision.reasons)}
        if decision.blocked:
            record.update(outcome="safety_blocked", answer=SAFE_RESPONSE)
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
    except Exception as exc:
        record.update(outcome="error", error_stage=stage, error_type=type(exc).__name__)
        code = getattr(exc, "code", None)
        record["error_code"] = code if type(code) is int else None
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
    finally:
        if observer is not None:
            record["attempts"] = observer.attempts
            record["fallback_used"] = len(observer.attempts) > 1
        record["timings_seconds"]["service_total"] = round(time.perf_counter() - started, 3)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", default=list(PILOT))
    parser.add_argument("--evaluation-date", type=date.fromisoformat, default=current_date())
    parser.add_argument("--corpus-revision", help="Identifier for the corpus uploaded to the live collection.")
    parser.add_argument("--run-id", help="New results folder name; existing folders are never overwritten.")
    parser.add_argument("--live", action="store_true", help="Explicitly allow Qdrant and Gemini requests.")
    args = parser.parse_args()
    cases, digest = load_cases()
    if len(set(args.cases)) != len(args.cases) or any(key not in cases for key in args.cases):
        parser.error("Choose unique case IDs from aq01 through aq40.")
    selected = [(cases[key], profile_dates(args.evaluation_date, cases[key]["target_months"]))
                for key in args.cases]
    for case, profile in selected:
        print(f"{case['id']} age={profile['completed_months']} routine={case['routine']}: {case['question']}")
    if not args.live:
        print("Preview only: no network calls or results written. Add --live to capture answers.")
        return
    if not args.corpus_revision or not args.corpus_revision.strip():
        parser.error("--corpus-revision is required for live capture; it is an asserted identifier, not remote verification.")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("coaching-%Y%m%dT%H%M%S%fZ")
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        parser.error("--run-id may contain only letters, numbers, hyphens and underscores.")
    output = PROJECT_ROOT / "eval" / "results" / run_id
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "rubric": "coaching-quality-v1", "question_set_version": QUESTION_SET_VERSION,
        "question_set_path": QUESTION_SET_PATH, "question_set_hash_method": "canonical-json-sha256",
        "question_set_sha256": digest, "code_revision": git_output("rev-parse", "HEAD"),
        "working_tree_status": git_output("status", "--porcelain", "--untracked-files=no"),
        "corpus_revision_asserted": args.corpus_revision, "collection": settings.QDRANT_COLLECTION,
        "primary_model": settings.GEMINI_MODEL, "fallback_model": settings.GEMINI_FALLBACK_MODEL,
        "retrieval_min_score": settings.RETRIEVAL_MIN_SCORE, "cases": args.cases,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    retrieval, coaching = RetrievalService(), CoachingService()
    for case, profile in selected:
        path = output / f"{case['id']}.json"
        path.write_text(json.dumps({"case": case, "outcome": "incomplete"}, indent=2) + "\n", encoding="utf-8")
        record = capture_case(case, profile, retrieval, coaching)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{case['id']}: {record['outcome']} ({record['timings_seconds']['service_total']}s)")
        if record["outcome"] == "error":
            print("Stopped after error; inspect the saved record before spending more quota.")
            break
    print(f"Saved to {output}")


if __name__ == "__main__":
    main()
