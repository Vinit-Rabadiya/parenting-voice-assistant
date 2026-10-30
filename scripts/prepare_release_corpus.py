"""Prepare source-checked everyday references without releasing clinical content."""
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from backend.services.age import current_date
from scripts.index_rag import load_passages, validate_source_references
from scripts.prepare_coverage_review import coverage_markdown
from scripts.build_reference_expansion import compile_expansion, fingerprint, replace_source_revisions

ROOT = Path(__file__).resolve().parents[1]


def extend_basic_care_release(base, manifest, pack):
    """Index the bounded runtime care selections, preserving every released record."""
    from backend.services.care_guidance import load_references
    if pack != load_references():
        raise ValueError("Care references must match the validated application input.")
    if any(p.get("clinical_review_required") or p.get("review_status") == "candidate_not_expert_validated"
           or p.get("release_status") == "blocked_pending_health_review" for p in base):
        raise ValueError("Base release contains blocked candidate content.")
    sources = list(manifest["sources"])
    selected = list(base)
    for key, source in pack["sources"].items():
        items = [(entry, reference) for entry in pack["entries"] for reference in entry["references"]
                 if reference["source"] == key]
        if not items:
            raise ValueError("Unused basic-care source.")
        sid = "basic-care-" + key
        if any(s["source_id"] == sid for s in sources):
            raise ValueError("Basic-care sources already exist in the base release.")
        digest = fingerprint({"source": source, "selections": items})
        title = source["publisher"] + ": " + source["title"]
        sources.append({"source_id": sid, "title": title, "publisher": source["publisher"],
                        "source_url": source["url"], "sha256": digest, "source_format": "web_summary",
                        "sections": sorted({r["section"] for _, r in items}),
                        "checked_on": pack["checked_on"], "language": "en"})
        for entry, reference in items:
            topic = entry["topic"]
            selected.append({
                "passage_id": f"basic-care-{entry['id']}-{key}", "source_id": sid,
                "source_title": title, "publisher": source["publisher"], "source_url": source["url"],
                "source_sha256": digest, "source_format": "web_summary", "pdf_page": None,
                "source_section": reference["section"], "title": reference["section"], "text": reference["text"],
                "content_sha256": hashlib.sha256(reference["text"].encode()).hexdigest(),
                "source_age": {"label": f"{entry['min_months']} to under {entry['max_months_exclusive']} months",
                               "min_months": entry["min_months"], "max_months_exclusive": entry["max_months_exclusive"]},
                "project_scope": {"min_months": 0, "max_months_inclusive": 24},
                "topic": topic, "developmental_domain": "nutrition" if topic == "feeding" else "safety" if topic in {"sleep", "outings"} else "common_concerns" if topic in {"reflux", "nappy_rash", "stomach_upset", "fever", "cough_cold", "teething", "stools", "jaundice", "development_concern"} else "responsive_caregiving",
                "routines": ["feeding"] if topic == "feeding" else [],
                "checked_on": pack["checked_on"], "review_status": "editorially_selected_not_expert_validated",
                "release_status": "basic_care_editorial_release", "clinical_review_required": False,
                "content_scope": pack["scope"], "reuse_status": "Short paraphrase; attribution retained",
            })
    if len({p["passage_id"] for p in selected}) != len(selected):
        raise ValueError("Duplicate release passage IDs.")
    return selected, {"schema_version": 1, "sources": sources}


def prepare_basic_care_release(base_dir, output_dir):
    from backend.services.care_guidance import load_references
    path = base_dir / "passages.jsonl"
    base = load_passages(path)
    validate_source_references(base, base_dir / "sources.json")
    pack = load_references()
    selected, sources = extend_basic_care_release(base, json.loads((base_dir / "sources.json").read_text(encoding="utf-8")), pack)
    if output_dir.exists():
        raise ValueError("Output exists; preserve the previous release.")
    output_dir.mkdir(parents=True)
    text = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in selected)
    (output_dir / "passages.jsonl").write_text(text, encoding="utf-8", newline="\n")
    (output_dir / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    validate_source_references(load_passages(output_dir / "passages.jsonl"), output_dir / "sources.json")
    report = {"schema_version": 1, "base_corpus_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "corpus_sha256": hashlib.sha256(text.encode()).hexdigest(), "passage_count": len(selected),
              "source_count": len(sources["sources"]), "added_passage_count": len(selected) - len(base),
              "care_pack_sha256": fingerprint(pack), "index_built": False, "review_status": pack["review_kind"],
              "clinical_candidates_activated": False}
    (output_dir / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "coverage.md").write_text(coverage_markdown(selected, current_date()), encoding="utf-8")
    return report


def revise_source(candidate, manifest, pack, revision, original_ids):
    """Refresh wording only; preserve passage identity, scope and clinical gates."""
    if fingerprint(pack) != revision["pack_sha256"]:
        raise ValueError("Source revision differs from its pinned review.")
    sid = revision["source_id"]
    old = {p["passage_id"]: p for p in candidate if p["source_id"] == sid}
    if (not old or set(old) & original_ids
            or any(p.get("clinical_review_required") or p.get("release_status") == "blocked_pending_health_review"
                   for p in old.values())):
        raise ValueError("Source revision cannot change the baseline or blocked clinical content.")
    sources = [s for s in pack["sources"] if s["source_id"] == sid]
    if len(sources) != 1:
        raise ValueError("Source revision requires one known source.")
    selected_pack = {**pack, "sources": sources, "replacement_sources": [sid]}
    retained, retained_manifest, _ = replace_source_revisions(selected_pack, candidate, manifest)
    revised, updated_manifest, _ = compile_expansion(selected_pack, retained, retained_manifest)
    updated = {p["passage_id"]: p for p in revised if p["source_id"] == sid}
    fields = ("source_age", "source_url", "developmental_domain", "routines", "applicability_conditions")
    if (set(updated) != set(old) or any(
            p.get("clinical_review_required") or p.get("release_status") == "blocked_pending_health_review"
            or any(p.get(field) != old[pid].get(field) for field in fields)
            for pid, p in updated.items())):
        raise ValueError("Source wording revision changed its identity, age, conditions or topic scope.")
    source_entries = {s["source_id"]: s for s in updated_manifest["sources"]}
    return ([updated.get(p["passage_id"], p) for p in candidate],
            {**manifest, "sources": [source_entries[s["source_id"]] for s in manifest["sources"]]})


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
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/everyday-release-v3")
    parser.add_argument("--base-release", type=Path, help="Extend a released corpus with validated basic-care references.")
    args = parser.parse_args()
    try:
        if args.base_release is not None:
            print(json.dumps(prepare_basic_care_release(args.base_release, args.output_dir), indent=2))
            return
        plan = json.loads(args.review.read_text(encoding="utf-8"))
        candidate_path = args.candidate_dir / "passages.jsonl"
        if hashlib.sha256(args.base.read_bytes()).hexdigest() != plan["base_corpus_sha256"]:
            raise ValueError("Base corpus revision differs from the editorial review.")
        candidate = load_passages(candidate_path)
        input_sha256 = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        if (input_sha256 != plan["candidate_corpus_sha256"]
                and fingerprint(candidate) != plan.get("revised_candidate_fingerprint")):
            raise ValueError("Candidate corpus revision differs from the editorial review.")
        validate_source_references(candidate, args.candidate_dir / "sources.json")
        sources = json.loads((args.candidate_dir / "sources.json").read_text(encoding="utf-8"))
        original = load_passages(args.base)
        checked_sources = {check["source_id"] for check in plan["source_checks"]}
        for revision in plan.get("source_revisions", []):
            if revision["source_id"] not in checked_sources:
                raise ValueError("Source revision requires an explicit source check.")
            pack_path = (ROOT / revision["pack"]).resolve()
            if not pack_path.is_relative_to(ROOT):
                raise ValueError("Source revision pack must be inside the project.")
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            candidate, sources = revise_source(candidate, sources, pack, revision,
                                                {p["passage_id"] for p in original})
        if (plan.get("revised_candidate_fingerprint")
                and fingerprint(candidate) != plan["revised_candidate_fingerprint"]):
            raise ValueError("Revised candidate differs from its pinned review.")
        selected = select_release_passages(candidate, original, plan, evaluated=current_date())
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
                  "candidate_corpus_sha256": input_sha256,
                  "effective_candidate_fingerprint": fingerprint(candidate),
                  "review_sha256": hashlib.sha256(args.review.read_bytes()).hexdigest(),
                  "source_revisions": plan.get("source_revisions", []),
                  "nonclinical_scope_corrections": sum(len(c["passage_ids"]) for c in plan.get("nonclinical_scope_corrections", [])),
                  "health_candidates_activated": False}
        (args.output_dir / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "coverage.md").write_text(coverage_markdown(selected, current_date()), encoding="utf-8")
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
