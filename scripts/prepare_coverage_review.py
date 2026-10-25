"""Prepare a local coverage audit and unlabelled review sheet; never query a model."""
import argparse
from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

from backend.services.retrieval import is_age_eligible
from backend.services.age import add_months, age_details, current_date
from scripts.evaluate_retrieval import query_age_context
from scripts.index_rag import load_passages, validate_source_references
from scripts.build_reference_expansion import DOMAINS

ROOT = Path(__file__).resolve().parents[1]
ROUTINES = ("feeding", "bathing", "play", "reading", "dressing", "sleep", "soothing")
AGES = (0, 2, 4, 6, 9, 12, 18, 24)


def apply_domain_review(passages, review, base_bytes):
    """Apply hash-pinned editorial labels to an audit copy, never the source corpus."""
    if (review.get("schema_version") != 1
            or review.get("status") != "editorial_classification_not_expert_validation"
            or review.get("base_corpus_sha256") != hashlib.sha256(base_bytes).hexdigest()):
        raise ValueError("Domain review does not match the original corpus revision.")
    original = {p["passage_id"]: p for p in (json.loads(line) for line in base_bytes.splitlines() if line.strip())}
    annotations = {}
    for pid, domains, anchor in review["annotations"]:
        if pid not in original or pid in annotations:
            raise ValueError("Domain review requires known unique passage IDs.")
        if (not isinstance(domains, list) or not domains or len(domains) != len(set(domains))
                or any(domain not in DOMAINS for domain in domains)):
            raise ValueError("Domain review requires distinct supported domains.")
        if not isinstance(anchor, str) or not anchor.strip() or anchor.casefold() not in original[pid]["text"].casefold():
            raise ValueError(f"Domain review anchor is absent from passage {pid}.")
        annotations[pid] = domains
    if set(annotations) != set(original):
        raise ValueError("Domain review must classify every original passage.")
    output = []
    for passage in passages:
        reviewed = annotations.get(passage["passage_id"])
        if reviewed and passage["text"] != original[passage["passage_id"]]["text"]:
            raise ValueError("Reviewed passage text changed; classify the new revision separately.")
        output.append({**passage, **({"developmental_domains": reviewed} if reviewed else {})})
    return output


def audit_findings(passages, evaluated):
    """Identify content/review risks; no counts imply semantic or clinical approval."""
    contained = []
    normalized = {p["passage_id"]: " ".join(re.findall(r"\w+", p["text"].casefold())) for p in passages}
    for index, first in enumerate(passages):
        for second in passages[index + 1:]:
            if first["source_id"] != second["source_id"]:
                continue
            left, right = normalized[first["passage_id"]], normalized[second["passage_id"]]
            if min(len(left), len(right)) >= 80 and (left in right or right in left):
                contained.append([first["passage_id"], second["passage_id"]])
    overdue, undated = set(), set()
    for passage in passages:
        due = passage.get("source_next_review_due")
        if due and date.fromisoformat(due) < evaluated:
            overdue.add(passage["source_id"])
        if not passage.get("checked_on"):
            undated.add(passage["source_id"])
    return {"contained_pairs": contained, "sources_past_review_due": sorted(overdue),
            "sources_without_check_date": sorted(undated),
            "health_review_blocked": sum(p.get("release_status") == "blocked_pending_health_review" for p in passages)}


def prepare_review(passages, inventory):
    """Count eligibility, not relevance; leave judgement fields explicitly unfilled."""
    cases = []
    for item in inventory["cases"]:
        case = {**item, "evaluation_date": inventory["evaluation_date"]}
        born = date.fromisoformat(case["date_of_birth"])
        evaluated = date.fromisoformat(case["evaluation_date"])
        if born > evaluated:
            raise ValueError("Birth date cannot follow the evaluation date.")
        # Out-of-scope cases test routing, not retrieval; do not fabricate an age.
        if item.get("category") == "out_of_scope":
            age, eligible = None, []
        else:
            age = query_age_context(case)
            eligible = [p["passage_id"] for p in passages if is_age_eligible(
                p["source_age"], age["completed_months"], child_age_days=age["child_age_days"])]
        cases.append({**case, "age_context": age, "age_eligible_passage_ids": eligible,
                      "expected_passage_ids": None, "expected_outcome": None,
                      "review_status": "pending", "review_notes": ""})
    return cases


def coverage_markdown(passages, evaluation_date=None):
    evaluation_date = evaluation_date or current_date()
    lines = ["# Candidate reference coverage", "",
             "Counts show age eligibility and routine tags, not semantic relevance, quality or clinical approval.",
             "Age 0 uses 11 days as a newborn example; other rows use completed months.",
             f"Evaluation date: {evaluation_date.isoformat()}. Ages use calendar dates, not average month lengths.",
             "Rows are selected checkpoints, not complete coverage of every day or month.", "",
             f"Total passages: {len(passages)}. Sources: {len({p['source_id'] for p in passages})}.", "",
             "| Age (months) | " + " | ".join(ROUTINES) + " |",
             "| --- | " + " | ".join("---" for _ in ROUTINES) + " |"]
    for months in AGES:
        birth = (evaluation_date - timedelta(days=11) if months == 0
                 else add_months(evaluation_date, -months))
        days, completed, _ = age_details(birth, evaluation_date)
        if completed != months or (months == 24 and add_months(birth, 24) != evaluation_date):
            raise ValueError("Choose an evaluation date that represents each exact age checkpoint.")
        eligible = [p for p in passages if is_age_eligible(
            p["source_age"], completed, child_age_days=days)]
        counts = [str(sum(routine in p.get("routines", []) for p in eligible)) for routine in ROUTINES]
        lines.append(f"| {months} | " + " | ".join(counts) + " |")
    domains = Counter(domain for p in passages for domain in p.get("developmental_domains", [
        p.get("developmental_domain", "not classified in original corpus")]))
    lines += ["", "## Domain inventory", "", "| Domain | Passages |", "| --- | --- |"]
    lines += [f"| {domain} | {count} |" for domain, count in sorted(domains.items())]
    findings = audit_findings(passages, evaluation_date)
    lines += ["", "Domain labels are non-exclusive editorial classifications, not expert approval.",
              "", "## Source and selection audit", "",
              f"Health-review-blocked candidate passages: {findings['health_review_blocked']}.",
              "Sources past the publisher's stated review date: " + (", ".join(findings["sources_past_review_due"]) or "none recorded") + ".",
              "Sources without a recorded check date: " + (", ".join(findings["sources_without_check_date"]) or "none") + ".",
              "A missing or future review date does not establish currency or Kenya applicability.",
              "", "### Same-source text containment", "",
              "Normalized text containment flags combined/standalone selections for review. It does not justify automatic deletion; source age eligibility can differ.", ""]
    lines += [f"- `{left}` / `{right}`" for left, right in findings["contained_pairs"]] or ["No containment pairs found."]
    lines += ["", "## Remaining review", "",
              "- A nonzero cell does not establish sufficient variety or correct retrieval.",
              "- Zero cells identify missing routine tags or missing content requiring investigation.",
              "- Review broad age overviews and follow-ups against actual passage text.",
              "- Health candidates remain blocked pending qualified review and country-specific routing.",
              "- Label relevant passages before retrieval; then freeze the development/held-out split.",
              "- Obtain parent/colleague wording separately; generated examples do not satisfy that requirement.",
              "- Do not claim Recall@4, MRR or semantic accuracy from this inventory.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "data/processed/activity-safety-candidates")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "eval/review/caregiver-coverage")
    parser.add_argument("--domain-review", type=Path, help="Apply an editorial classification to the audit only.")
    parser.add_argument("--audit-only", action="store_true", help="Print the coverage audit without writing question labels or files.")
    parser.add_argument("--evaluation-date", type=date.fromisoformat, help="Calendar date for the printed coverage audit.")
    args = parser.parse_args()
    corpus_path = args.corpus_dir / "passages.jsonl"
    passages = load_passages(corpus_path)
    validate_source_references(passages, args.corpus_dir / "sources.json")
    if args.domain_review:
        passages = apply_domain_review(passages, json.loads(args.domain_review.read_text(encoding="utf-8")),
                                       (ROOT / "data/processed/rag/passages.jsonl").read_bytes())
    inventory = json.loads((ROOT / "data/evaluation/coverage-questions.json").read_text(encoding="utf-8"))
    if args.audit_only:
        print(coverage_markdown(passages, args.evaluation_date or date.fromisoformat(inventory["evaluation_date"])))
        return
    cases = prepare_review(passages, inventory)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Never replace completed labels or an earlier review record.
    targets = [args.output_dir / name for name in ("coverage.md", "question-review.json")]
    if any(path.exists() for path in targets):
        parser.error("Output already exists; choose a new --output-dir to preserve review work.")
    evaluated = date.fromisoformat(inventory["evaluation_date"])
    targets[0].write_text(coverage_markdown(passages, evaluated), encoding="utf-8")
    targets[1].write_text(json.dumps({
        "status": "labels_and_split_pending", "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "instructions": "Eligible IDs are not relevance labels. Read the corpus before assigning expected IDs and outcomes. No retrieval results have been examined by this script.",
        "cases": cases,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared coverage and {len(cases)} unlabelled review cases in {args.output_dir}")


if __name__ == "__main__":
    main()
