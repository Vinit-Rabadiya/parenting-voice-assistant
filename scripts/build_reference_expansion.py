"""Build a separate candidate corpus from versioned editorial source summaries.

No downloads, embeddings, model calls, or cloud writes occur here. The summary
fingerprint identifies the editorial source entry, not the publisher's HTML.
"""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
from io import BytesIO
from urllib.parse import urlparse

from pypdf import PdfReader

from scripts.build_rag_passages import build_coverage_matrix
from scripts.index_rag import load_passages, validate_age_metadata, validate_source_references

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {"cognitive", "language", "gross_motor", "fine_motor", "social_emotional",
           "responsive_caregiving", "nutrition", "safety", "immunisation", "common_concerns"}
HOSTS = {"www.unicef.org", "www.nhs.uk", "www.who.int", "www.health.go.ke", "health.go.ke", "www.publichealth.hscni.net"}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compile_expansion(pack: dict, base: list[dict], manifest: dict, *, pdf_dir: Path = ROOT / "data/raw/pdfs") -> tuple[list[dict], dict, dict]:
    if pack.get("schema_version") != 1 or pack.get("status") != "candidate_not_expert_validated":
        raise ValueError("Unsupported reference pack or review status.")
    date.fromisoformat(pack["checked_on"])
    health_review = pack.get("clinical_review_required", False)
    if type(health_review) is not bool:
        raise ValueError("clinical_review_required must be a boolean.")
    sources = list(manifest["sources"])
    known_sources = {source["source_id"] for source in sources}
    passages = list(base)
    additions = []
    for source in pack["sources"]:
        sid = source["source_id"]
        if not isinstance(sid, str) or not sid.strip() or sid in known_sources:
            raise ValueError("Invalid or duplicate expansion source ID.")
        known_sources.add(sid)
        url = urlparse(source["source_url"])
        if url.scheme != "https" or url.hostname not in HOSTS or url.username or url.password:
            raise ValueError("Expansion sources require an approved HTTPS publisher.")
        for field in ("title", "publisher"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise ValueError(f"Missing source {field}.")
        if not source["passages"]:
            raise ValueError("Expansion source has no passages.")
        pdf = None
        source_format = source.get("source_format", "web_summary")
        if source_format not in {"web_summary", "pdf_summary"}:
            raise ValueError("Unknown reference source format.")
        if source_format == "pdf_summary":
            filename = source["filename"]
            if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith(".pdf"):
                raise ValueError("PDF source requires a plain PDF filename.")
            raw = (pdf_dir / filename).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != source["sha256"]:
                raise ValueError("PDF source fingerprint changed; review before rebuilding.")
            pdf = PdfReader(BytesIO(raw))
            if len(pdf.pages) != source["expected_pages"]:
                raise ValueError("PDF source page count changed.")
        else:
            digest = fingerprint(source)
        source_entry = {"source_id": sid, "title": source["title"], "publisher": source["publisher"],
                        "source_url": source["source_url"], "source_format": "web_summary",
                        "sha256": digest, "fingerprint_basis": "canonical_editorial_source_entry",
                        "checked_on": pack["checked_on"], "reuse_status": "editorial summaries; publisher rights retained",
                        "sections": sorted({item["section"] for item in source["passages"]})}
        if pdf is not None:
            source_entry.update({"source_format": "pdf_summary", "filename": filename,
                                 "expected_pages": len(pdf.pages), "fingerprint_basis": "original_pdf_bytes"})
        sources.append(source_entry)
        for item in source["passages"]:
            if item.get("domain") in {"immunisation", "common_concerns"} and not health_review:
                raise ValueError("Health education requires an explicit clinical review gate.")
            if health_review and ("country" not in source or source["country"] not in (None, "KE")):
                raise ValueError("Health sources require an explicit supported country or null for general education.")
            low, high = item.get("age", source["age"])
            if type(low) is not int or type(high) is not int or not 0 <= low < high <= 25:
                raise ValueError("Invalid expansion age interval.")
            if low < source["age"][0] or high > source["age"][1]:
                raise ValueError("Passage ages extend beyond selected source ages.")
            text, section = item["text"], item["section"]
            if not isinstance(text, str) or not 40 <= len(text.strip()) <= 1200:
                raise ValueError("Expansion passage must contain 40–1200 characters.")
            if not isinstance(section, str) or not section.strip() or item["domain"] not in DOMAINS:
                raise ValueError("Invalid source section or developmental domain.")
            page_number, page_digest = None, None
            if pdf is not None:
                page_number = item["pdf_page"]
                if type(page_number) is not int or not 1 <= page_number <= len(pdf.pages):
                    raise ValueError("Selected PDF page is outside the document.")
                page_text = " ".join((pdf.pages[page_number - 1].extract_text() or "").split())
                anchor = item.get("source_anchor")
                if not isinstance(anchor, str) or not anchor.strip() or anchor not in page_text:
                    raise ValueError("Selected PDF section anchor was not found.")
                page_digest = hashlib.sha256(page_text.encode()).hexdigest()
            record = {
                "passage_id": hashlib.sha256(f"{sid}:{section}".encode()).hexdigest()[:20],
                "text": text, "title": section, "source_id": sid, "source_title": source["title"],
                "publisher": source["publisher"], "source_url": source["source_url"],
                "source_sha256": digest, "source_format": source_format, "source_section": section,
                "pdf_page": page_number, "source_age": {"label": f"{low} to under {high} months", "min_months": low,
                                                   "max_months_exclusive": high},
                "project_scope": {"min_months": 0, "max_months_inclusive": 24},
                "topic": item["domain"], "developmental_domain": item["domain"], "routines": item["routines"],
                "checked_on": pack["checked_on"], "review_status": "candidate_not_expert_validated",
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "reuse_status": "short editorial summary; attribution retained",
            }
            if pdf is not None:
                record.update({"source_anchor": item["source_anchor"], "normalized_page_sha256": page_digest,
                               "source_filename": filename})
            if health_review:
                record.update({"clinical_review_required": True, "country": source["country"],
                               "release_status": "blocked_pending_health_review",
                               "content_scope": "health_education_candidate"})
            validate_age_metadata(record)
            additions.append(record)
    passages.extend(additions)
    for field in ("passage_id", "content_sha256"):
        values = [p[field] for p in passages]
        if len(set(values)) != len(values):
            raise ValueError(f"Duplicate {field}; review source selections.")
    report = {
        "schema_version": 1, "review_status": "candidate_not_expert_validated", "index_built": False,
        "base_passage_count": len(base), "added_passage_count": len(additions), "passage_count": len(passages),
        "reference_pack_sha256": fingerprint(pack), "base_corpus_sha256": fingerprint(base),
        "added_domains": dict(sorted(Counter(p["developmental_domain"] for p in additions).items())),
        "coverage_matrix": build_coverage_matrix(passages),
        "pending_sources": pack.get("pending_sources", []),
        "latency_evidence": "Not measured. Online search and corpus preparation are not part of live requests.",
        "clinical_review_required": health_review,
    }
    return passages, {"schema_version": 1, "sources": sources}, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=ROOT / "data/reference-expansion.json")
    parser.add_argument("--base", type=Path, default=ROOT / "data/processed/rag/passages.jsonl")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/sources.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/expanded")
    args = parser.parse_args()
    try:
        base = load_passages(args.base)
        validate_source_references(base, args.manifest)
        pack = json.loads(args.pack.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        passages, expanded_manifest, report = compile_expansion(pack, base, manifest)
        # Validate before writing; a bad pack cannot replace the working corpus.
        from scripts.index_rag import validate_routine_metadata, validate_source_metadata
        for passage in passages:
            validate_source_metadata(passage)
            validate_routine_metadata(passage)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, value in (("sources.json", expanded_manifest), ("preparation-report.json", report)):
            (args.output_dir / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (args.output_dir / "passages.jsonl").write_text(
            "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in passages), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Reference expansion failed: {exc}\n")
    print(f"Candidate corpus: {len(base)} existing + {report['added_passage_count']} new = {len(passages)} passages.")
    print(f"Saved to {args.output_dir}. Not uploaded; health-professional validation remains outstanding.")


if __name__ == "__main__":
    main()
