"""Prepare source-checked everyday references without releasing clinical content."""
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from backend.services.age import current_date
from scripts.index_rag import load_passages, validate_source_references
from scripts.prepare_coverage_review import coverage_markdown

ROOT = Path(__file__).resolve().parents[1]


def select_release_passages(candidate, original, plan, *, evaluated):
    if (plan.get("schema_version") != 1
            or plan.get("review_kind") != "editorial_source_check_not_clinical_validation"
            or plan.get("country") != "KE" or plan.get("language") != "English"):
        raise ValueError("Unsupported everyday release review.")
    checked = date.fromisoformat(plan["checked_on"])
    interval = plan["review_interval_days"]
    if type(interval) is not int or not 1 <= interval <= 90 or not checked <= evaluated <= checked + timedelta(days=interval):
        raise ValueError("Everyday source review is future-dated or requires refresh.")
    checks = {}
    for check in plan["source_checks"]:
        sid = check["source_id"]
        if sid in checks or not check.get("finding", "").strip():
            raise ValueError("Source checks require unique sources and findings.")
        due = check.get("source_next_review_due")
        if due and date.fromisoformat(due) < evaluated:
            raise ValueError("Source is past its stated review date.")
        checks[sid] = check
    baseline = {p["passage_id"]: p for p in original}
    corrections = {}
    for correction in plan.get("nonclinical_scope_corrections", []):
        sid = correction["source_id"]
        if sid not in checks or not correction.get("reason", "").strip():
            raise ValueError("Scope corrections require a checked source and explicit rationale.")
        for pid in correction["passage_ids"]:
            if pid in corrections or pid in baseline:
                raise ValueError("Scope corrections require unique added passage IDs.")
            corrections[pid] = sid
    corrected_sources = set(corrections.values())
    selected, additions, retained, used, corrected = [], 0, set(), set(), set()
    for passage in candidate:
        pid, sid = passage["passage_id"], passage["source_id"]
        if pid in baseline:
            if passage != baseline[pid] or pid in retained:
                raise ValueError("Release must preserve the exact existing baseline records.")
            retained.add(pid)
            selected.append(dict(passage))
        elif sid in checks and (sid not in corrected_sources or pid in corrections):
            correction = corrections.get(pid)
            domain = passage.get("developmental_domain")
            if correction and (correction != sid or domain not in {
                "language", "cognitive", "social_emotional", "responsive_caregiving", "fine_motor", "gross_motor",
            }):
                raise ValueError("Scope corrections are limited to explicitly reviewed nonclinical development.")
            if (domain in {"immunisation", "common_concerns"}
                    or (not correction and (
                        passage.get("clinical_review_required") is not None and passage["clinical_review_required"] is not False
                        or passage.get("release_status") == "blocked_pending_health_review"))):
                raise ValueError("Health-review candidates cannot enter an everyday release.")
            if passage["source_url"] != checks[sid]["url"]:
                raise ValueError("Source check URL differs from the selected passage.")
            used.add(sid)
            released = {**passage, "review_status": "editorially_selected_not_expert_validated",
                             "editorial_reviewed_on": checked.isoformat(),
                             "editorial_review_kind": plan["review_kind"]}
            if correction:
                corrected.add(pid)
                released.update(clinical_review_required=False, release_status="nonclinical_editorial_release",
                                original_release_status=passage.get("release_status"),
                                scope_classification="nonclinical_development_source_checked")
            selected.append(released)
            additions += 1
    if (retained != set(baseline) or used != set(checks) or additions != plan["expected_additions"]
            or corrected != set(corrections)):
        raise ValueError("Release selection differs from the pinned review inventory.")
    if len({p["passage_id"] for p in selected}) != len(selected):
        raise ValueError("Release contains duplicate passage IDs.")
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, default=ROOT / "data/processed/practical-care-activity-candidates")
    parser.add_argument("--base", type=Path, default=ROOT / "data/processed/rag/passages.jsonl")
    parser.add_argument("--review", type=Path, default=ROOT / "data/everyday-release-review.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/everyday-release-v1")
    args = parser.parse_args()
    try:
        plan = json.loads(args.review.read_text(encoding="utf-8"))
        candidate_path = args.candidate_dir / "passages.jsonl"
        for path, field in ((args.base, "base_corpus_sha256"), (candidate_path, "candidate_corpus_sha256")):
            if hashlib.sha256(path.read_bytes()).hexdigest() != plan[field]:
                raise ValueError("Corpus revision differs from the editorial review.")
        candidate = load_passages(candidate_path)
        validate_source_references(candidate, args.candidate_dir / "sources.json")
        selected = select_release_passages(candidate, load_passages(args.base), plan, evaluated=current_date())
        sources = json.loads((args.candidate_dir / "sources.json").read_text(encoding="utf-8"))
        used = {p["source_id"] for p in selected}
        sources["sources"] = [s for s in sources["sources"] if s["source_id"] in used]
        if args.output_dir.exists():
            raise ValueError("Output already exists; use a new directory to preserve earlier evidence.")
        args.output_dir.mkdir(parents=True)
        text = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in selected)
        (args.output_dir / "passages.jsonl").write_text(text, encoding="utf-8", newline="\n")
        (args.output_dir / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
        validate_source_references(load_passages(args.output_dir / "passages.jsonl"), args.output_dir / "sources.json")
        report = {"schema_version": 1, "review_status": plan["review_kind"], "index_built": False,
                  "passage_count": len(selected), "source_count": len(used),
                  "corpus_sha256": hashlib.sha256(text.encode()).hexdigest(),
                  "base_corpus_sha256": plan["base_corpus_sha256"],
                  "candidate_corpus_sha256": plan["candidate_corpus_sha256"],
                  "review_sha256": hashlib.sha256(args.review.read_bytes()).hexdigest(),
                  "nonclinical_scope_corrections": sum(len(c["passage_ids"]) for c in plan.get("nonclinical_scope_corrections", [])),
                  "health_candidates_activated": False}
        (args.output_dir / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "coverage.md").write_text(coverage_markdown(selected, current_date()), encoding="utf-8")
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
