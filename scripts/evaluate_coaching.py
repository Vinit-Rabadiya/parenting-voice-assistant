"""Capture synthetic coaching evaluation cases; preview by default, opt in to live calls."""

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
from math import isfinite
import re
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

from backend.core.config import PROJECT_ROOT, settings
from backend.services.age import add_months, age_details, current_date, message_age_months, within_project_scope
from backend.services.coaching import CoachingService, PROMPT_VERSION, PROMPT_SHA256, determine_answer_budget
from backend.services.evidence import select_evidence
from backend.services.care_guidance import select_care_references
from backend.services.care_response import conversation_boundary_response
from backend.services.vaccination import inspect_vaccination
from backend.services.conversation_context import (
    caregiver_request, contextual_age_months, contextual_retrieval_query,
    needs_topic_clarification, select_conversation_context, semantic_retrieval_query,
)
from backend.services.care_response import professional_assessment_response
from scripts.evaluate_retrieval import load_queries, query_age_context
from backend.services.retrieval import RetrievalService
from backend.services.response_safety import SAFE_RESPONSE, review_coaching_result
from backend.services.input_safety import inspect_input
from backend.services.crisis_safety import inspect_crisis


QUESTION_SET_VERSION = "coaching-quality-v1"
QUESTION_SET_PATH = "data/evaluation/coaching-questions.json"
PILOT = ("aq01", "aq10", "aq21", "aq32")


def keyword_search_text(text: str) -> str:
    """Evaluation-only keyword baseline; never rewrite the message sent to generation."""
    stop_words = {"how", "can", "could", "i", "we", "you", "my", "our", "the", "a", "an",
                  "is", "are", "it", "to", "do", "does", "what", "please", "help", "make",
                  "try", "more", "some", "any", "me", "and", "in", "at"}
    words = re.findall(r"[^\W_]+(?:['.][^\W_]+)*", text.lower().replace("\u2019", "'"))
    return " ".join(word for word in words if word not in stop_words) or text.strip()


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


def load_retrieval_capture_cases(path: Path, selected_ids: list[str] | None = None):
    """Reuse frozen development queries without copying a second question set."""
    queries = [case for case in load_queries(path) if case.get("split") == "development"]
    known = {case["id"] for case in queries}
    if len(known) != len(queries) or not known:
        raise ValueError("Development capture requires unique development case IDs.")
    if selected_ids is not None and (len(selected_ids) != len(set(selected_ids)) or not set(selected_ids) <= known):
        raise ValueError("Choose unique IDs from the development split only.")
    selected = []
    for query in queries:
        if selected_ids is not None and query["id"] not in selected_ids:
            continue
        if not query.get("corpus_sha256"):
            raise ValueError("Development capture requires a pinned corpus fingerprint.")
        age = query_age_context(query)
        case = {"id": query["id"], "question": query["query"], "routine": query.get("routine"),
                "expected_behaviour": query.get("notes", "Requires independent answer review"),
                "corpus_sha256": query["corpus_sha256"]}
        profile = {"evaluation_date": age["evaluation_date"], "date_of_birth": age["date_of_birth"],
                   "age_days": age["child_age_days"], "completed_months": age["completed_months"],
                   "age_months": age["child_age_months"]}
        selected.append((case, profile))
    return selected, hashlib.sha256(path.read_bytes()).hexdigest()


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
            candidates = getattr(response, "candidates", None) or []
            attempt["finish_reasons"] = [str(getattr(candidate, "finish_reason", None))
                                         for candidate in candidates]
            feedback = getattr(response, "prompt_feedback", None)
            attempt["prompt_block_reason"] = str(getattr(feedback, "block_reason", None))
            attempt["has_text"] = bool((getattr(response, "text", None) or "").strip())
            return response
        except Exception as exc:
            attempt["outcome"] = "error"
            attempt["error_type"] = type(exc).__name__
            code = getattr(exc, "code", None)
            attempt["error_code"] = code if type(code) is int else None
            raise
        finally:
            attempt["seconds"] = round(time.perf_counter() - started, 3)


def capture_case(case, profile, retrieval, coaching, *, messages=None, retrieval_only=False,
                 keyword_search=False):
    context = select_conversation_context(messages or [])
    record = {
        "case": case, "profile": profile, "outcome": "incomplete",
        "retrieved": [], "supplied_evidence": [], "attempts": [],
        "answer": None, "selected_model": None, "fallback_used": False,
        "timings_seconds": {}, "ratings": None, "audio_playback": "not_checked",
        "limitations": "Direct service evaluation: excludes authentication, Firestore, ASR and TTS.",
        "conversation_context": context,
        "requested_word_limit": determine_answer_budget(case["question"], context).word_limit,
        "caregiver_request": caregiver_request(case["question"], context),
    }
    started = time.perf_counter()
    explicit_age = message_age_months(case["question"])
    age_source = "message" if explicit_age is not None else "profile"
    outside_age_range = not within_project_scope(date.fromisoformat(profile["date_of_birth"]),
                                                 date.fromisoformat(profile["evaluation_date"]))
    if explicit_age is not None:
        outside_age_range = False
        profile = {**profile, "age_months": explicit_age, "completed_months": int(explicit_age),
                   "age_days": round(explicit_age * 30.4375)}
    stage = "retrieval"
    observer = None
    try:
        query = contextual_retrieval_query(case["question"], context)
        if explicit_age is None:
            context_age = contextual_age_months(case["question"], context)
            if context_age is not None:
                age_source = "conversation"
                outside_age_range = False
                profile = {**profile, "age_months": context_age, "completed_months": int(context_age),
                           "age_days": round(context_age * 30.4375)}
        record["subject_age"] = {key: profile[key] for key in ("age_months", "completed_months", "age_days")}
        record["subject_age"]["source"] = age_source
        record["subject_age"]["override"] = profile["age_months"] if age_source != "profile" else None
        tick = time.perf_counter()
        stage = "input_safety"
        crisis = inspect_crisis(case["question"])
        triage = inspect_input(case["question"], profile["completed_months"], child_age_days=profile["age_days"])
        record["caregiver_safety"] = {"kind": crisis.kind, "reasons": list(crisis.reasons)}
        record["input_safety"] = {"escalate": triage.escalate, "reasons": list(triage.reasons)}
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        if triage.escalate or crisis.kind:
            record.update(outcome="escalated" if triage.escalate else crisis.kind,
                          answer=triage.answer if triage.escalate else crisis.answer,
                          referral_sources=list(triage.citations))
            return record
        unresolved_follow_up = needs_topic_clarification(case["question"], context)
        boundary = conversation_boundary_response(
            case["question"], child_age_months=profile["age_months"],
            outside_age_range=outside_age_range, unresolved_follow_up=unresolved_follow_up,
        )
        if boundary is not None:
            record.update(outcome="no_evidence", answer=boundary.answer, response_kind=boundary.kind,
                          clarification_field=boundary.clarification_field)
            return record
        vaccination = inspect_vaccination(case["question"], profile["age_months"], topic=query)
        if vaccination is not None:
            record.update(outcome="vaccination_notice", answer=vaccination.answer, vaccination_country="KE")
            record["reference_sources"] = [
                {"title": source.title, "url": source.url, "pdf_page": source.pdf_page}
                for source in vaccination.sources
            ]
            return record
        assessment = professional_assessment_response(case["question"])
        if assessment is not None:
            record.update(outcome="no_evidence", answer=assessment.answer, response_kind=assessment.kind)
            return record
        stage = "retrieval"
        tick = time.perf_counter()
        semantic_query = semantic_retrieval_query(case["question"], context)
        search_text = keyword_search_text(semantic_query) if keyword_search else semantic_query
        record["search_query"] = search_text
        reference_status = "no_match"
        # Retrieval experiments retain their vector query; ordinary answer capture
        # follows the API's local-reference path without an unused cloud search.
        local_references = (select_care_references(case["question"], profile["age_months"], context, [])
                            if not retrieval_only and not keyword_search else [])
        try:
            passages = [] if local_references else retrieval.retrieve(
                search_text, profile["completed_months"], case["routine"], 3,
                child_age_days=profile["age_days"],
            )
        except Exception as exc:
            reference_status = "unavailable"
            record["retrieval_error_type"] = type(exc).__name__
            passages = []
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        record["retrieved"] = [asdict(p) for p in passages]
        stage = "evidence_selection"
        tick = time.perf_counter()
        evidence = select_evidence(passages, settings.RETRIEVAL_MIN_SCORE)
        record["vector_evidence"] = [asdict(p) for p in evidence]
        if not retrieval_only:
            evidence = local_references or select_care_references(case["question"], profile["age_months"], context, evidence)
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        record["supplied_evidence"] = [asdict(p) for p in evidence]
        record["reference_status"] = "matched" if evidence and reference_status != "unavailable" else reference_status
        if retrieval_only:
            record.update(outcome="evidence_available" if evidence else "no_evidence")
            return record
        stage = "generation"
        tick = time.perf_counter()
        observer = CaptureModels(coaching.client.models)
        service = CoachingService(
            model=coaching.model, fallback_model=coaching.fallback_model,
            client=SimpleNamespace(models=observer),
        )
        result = service.generate(case["question"], profile["age_months"], case["routine"], evidence,
                                  **({"conversation_context": context} if context else {}))
        record["timings_seconds"][stage] = round(time.perf_counter() - tick, 3)
        record["selected_model"] = observer.attempts[-1]["model"]
        stage = "response_safety"
        tick = time.perf_counter()
        result, decision = review_coaching_result(result, evidence, profile["age_months"], case["question"], context)
        record.update(outcome="answered", answer=result.answer, answer_basis=result.answer_basis)
        record["safety"] = {"blocked": decision.blocked, "reasons": list(decision.reasons),
                            "replaced_with_basic_care": decision.replaced_with_basic_care}
        record["delivered_references"] = [asdict(p) for p in result.passages]
        if decision.blocked:
            record.update(outcome="safety_blocked", answer=result.answer if result.blocked else SAFE_RESPONSE)
        record["answer_word_count"] = len(record["answer"].split())
        record["within_requested_word_limit"] = record["answer_word_count"] <= record["requested_word_limit"]
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
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--retrieval-cases", type=Path,
                        help="Capture answers for selected development IDs in a pinned retrieval export.")
    parser.add_argument("--evaluation-date", type=date.fromisoformat, default=current_date())
    parser.add_argument("--corpus-revision", help="Identifier for the corpus uploaded to the live collection.")
    parser.add_argument("--run-id", help="New results folder name; existing folders are never overwritten.")
    parser.add_argument("--live", action="store_true", help="Explicitly allow Qdrant and Gemini requests.")
    parser.add_argument("--request-interval", type=float, default=0,
                        help="Minimum seconds between evaluation cases, excluded from service latency.")
    parser.add_argument("--collection", default=settings.QDRANT_COLLECTION,
                        help="Evaluate a separate staging collection without changing application settings.")
    parser.add_argument("--allow-candidate-content", action="store_true",
                        help="Inspect unapproved references in a separate evaluation collection only.")
    parser.add_argument("--follow-up", action="append", default=[],
                        help="Capture an additional synthetic turn after each case; may be repeated.")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="Record routing and reference matches without calling the generation model.")
    parser.add_argument("--keyword-search", action="store_true",
                        help="Compare evaluation-only search keyword extraction; production requests are unchanged.")
    args = parser.parse_args()
    if not isfinite(args.request_interval) or not 0 <= args.request_interval <= 60:
        parser.error("Request interval must be a finite number from 0 to 60 seconds.")
    if args.allow_candidate_content and args.collection == settings.QDRANT_COLLECTION:
        parser.error("Candidate content requires a separate evaluation collection.")
    if any(not text.strip() for text in args.follow_up) or len(args.follow_up) > 3:
        parser.error("Choose at most three nonempty follow-up messages.")
    if args.retrieval_only and args.follow_up:
        parser.error("Retrieval-only runs cannot provide generated answers for follow-up context.")
    if args.retrieval_cases:
        try:
            selected, digest = load_retrieval_capture_cases(args.retrieval_cases, args.cases)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        question_path = str(args.retrieval_cases)
        question_version, hash_method = "retrieval-development-capture-v1", "file-bytes-sha256"
    else:
        cases, digest = load_cases()
        ids = args.cases or list(PILOT)
        if len(set(ids)) != len(ids) or any(key not in cases for key in ids):
            parser.error("Choose unique case IDs from aq01 through aq40.")
        selected = [(cases[key], profile_dates(args.evaluation_date, cases[key]["target_months"])) for key in ids]
        question_path = QUESTION_SET_PATH
        question_version, hash_method = QUESTION_SET_VERSION, "canonical-json-sha256"
    for case, profile in selected:
        print(f"{case['id']} age={profile['completed_months']} routine={case['routine']}: {case['question']}")
        for follow_up in args.follow_up:
            print(f"  Follow-up: {follow_up}")
    if not args.live:
        print("Preview only: no network calls or results written. Add --live to capture answers.")
        return
    if not args.corpus_revision or not args.corpus_revision.strip():
        parser.error("--corpus-revision is required for live capture; it is an asserted identifier, not remote verification.")
    if args.retrieval_cases and any(args.corpus_revision != f"sha256:{case['corpus_sha256']}" for case, _ in selected):
        parser.error("The asserted corpus revision must match the pinned development export.")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("coaching-%Y%m%dT%H%M%S%fZ")
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        parser.error("--run-id may contain only letters, numbers, hyphens and underscores.")
    output = PROJECT_ROOT / "eval" / "results" / run_id
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "rubric": "coaching-quality-v1", "question_set_version": question_version,
        "prompt_version": PROMPT_VERSION, "prompt_sha256": PROMPT_SHA256,
        "question_set_path": question_path, "question_set_hash_method": hash_method,
        "question_set_sha256": digest, "code_revision": git_output("rev-parse", "HEAD"),
        "working_tree_status": git_output("status", "--porcelain", "--untracked-files=no"),
        "corpus_revision_asserted": args.corpus_revision, "collection": args.collection,
        "provider": settings.COACHING_PROVIDER,
        "primary_model": settings.coaching_model, "fallback_model": settings.coaching_fallback_model,
        "retrieval_min_score": settings.RETRIEVAL_MIN_SCORE, "cases": [case["id"] for case, _ in selected],
        "retrieval_limit": 3,
        "follow_up_messages": args.follow_up,
        "retrieval_only": args.retrieval_only,
        "request_interval_seconds": args.request_interval,
        "keyword_search": args.keyword_search,
        "candidate_content_allowed": args.allow_candidate_content,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    retrieval = RetrievalService(collection_name=args.collection, allow_candidate_content=args.allow_candidate_content,
                                 cache_ttl_seconds=0)
    coaching = CoachingService()
    last_started = None
    for case, profile in selected:
        if last_started is not None:
            time.sleep(max(0, args.request_interval - (time.monotonic() - last_started)))
        last_started = time.monotonic()
        path = output / f"{case['id']}.json"
        path.write_text(json.dumps({"case": case, "outcome": "incomplete"}, indent=2) + "\n", encoding="utf-8")
        record = capture_case(case, profile, retrieval, coaching, retrieval_only=args.retrieval_only,
                              keyword_search=args.keyword_search)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{case['id']}: {record['outcome']} ({record['timings_seconds']['service_total']}s)")
        if record["outcome"] == "error":
            print("Stopped after error; inspect the saved record before spending more quota.")
            break
        messages = []
        for number, question in enumerate(args.follow_up, start=1):
            time.sleep(max(0, args.request_interval - (time.monotonic() - last_started)))
            last_started = time.monotonic()
            assistant = {"role": "assistant", "text": record["answer"], "status": record["outcome"],
                         "response_kind": record.get("response_kind"),
                         "caregiver_request": record["caregiver_request"],
                         "clarification_field": record.get("clarification_field"),
                         "subject_age_override": record["subject_age"]["override"],
                         "citations": record.get("reference_sources", [])}
            messages.extend([
                {"role": "user", "text": record["case"]["question"]},
                assistant,
            ])
            follow_case = {**case, "id": f"{case['id']}-f{number}", "question": question,
                           "expected_behaviour": "Review context use, supported alternatives and safety boundaries."}
            record = capture_case(follow_case, profile, retrieval, coaching, messages=messages,
                                  keyword_search=args.keyword_search)
            (output / f"{follow_case['id']}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{follow_case['id']}: {record['outcome']} ({record['timings_seconds']['service_total']}s)")
            if record["outcome"] == "error":
                break
        if record["outcome"] == "error":
            print("Stopped after follow-up error; inspect the saved record before spending more quota.")
            break
    print(f"Saved to {output}")


if __name__ == "__main__":
    main()
