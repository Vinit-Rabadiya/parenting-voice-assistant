# reads data/sources.json and local pdfs, then writes page records for build_rag_passages.py.
# run this script before the passage builder; the two scripts exchange data through files.
import argparse
import hashlib
import json
from pathlib import Path

import pypdf
from pypdf import PdfReader


# locate the repository from this file so default paths do not depend on the terminal folder.
ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    # turn a python dictionary or list into readable utf-8 json on disk.
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_sources(manifest_path: Path, raw_dir: Path, output_dir: Path) -> dict:
    # load the source inventory; each entry identifies one expected pdf.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported source manifest version")
    sources = manifest["sources"]
    # a set removes duplicates, so different lengths reveal repeated source ids.
    ids = [source["source_id"] for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source ids")

    # validate all inputs before creating extraction output.
    inputs = []
    for source in sources:
        source_id = source["source_id"]
        if not source_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in source_id):
            raise ValueError(f"invalid source id: {source_id}")
        filename = source["filename"]
        if Path(filename).name != filename:
            raise ValueError("source filename must be a basename")
        path = raw_dir / filename
        # compare file fingerprints before applying selections written for a specific pdf.
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected_hash = source.get("sha256")
        if expected_hash and digest != expected_hash:
            raise ValueError(f"source hash changed: {source_id}; review the source before proceeding")
        reader = PdfReader(path)
        if len(reader.pages) != source["expected_pages"]:
            raise ValueError(f"unexpected page count: {source_id}")
        # keep metadata, fingerprint, and reader together for the extraction loop.
        inputs.append((source, digest, reader))

    output_dir.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "extractor": f"pypdf {pypdf.__version__}", "sources": []}
    for source, digest, reader in inputs:
        source_dir = output_dir / source["source_id"]
        source_dir.mkdir(exist_ok=True)
        low_text_pages = []
        review_text = []
        plain_review = []
        for number, page in enumerate(reader.pages, start=1):
            # keep both reading orders because columns may extract differently in each mode.
            text = page.extract_text() or ""
            # completely blank pages can lack the content stream required by layout extraction.
            layout_text = (page.extract_text(extraction_mode="layout") or "") if page.get_contents() is not None else ""
            record = {
                "source_id": source["source_id"],
                "source_sha256": digest,
                "pdf_page": number,
                "pdf_page_label": reader.page_labels[number - 1],
                "text": text,
                "layout_text": layout_text,
                "non_whitespace_characters": len("".join(text.split())),
                "review_status": "unreviewed",
                "page_rotation": page.rotation,
                "layout_warning": "layout extraction can omit rotated text; compare plain text and PDF",
            }
            # retain only page numbers needed by the report, not another copy of all page records.
            if record["non_whitespace_characters"] < 40:
                low_text_pages.append(number)
            # pad page numbers with zeroes, for example page-041.json, for predictable lookup.
            write_json(source_dir / f"page-{number:03d}.json", record)
            review_text.append(f"\n## PDF page {number}\n\n{layout_text}\n")
            plain_review.append(f"\n## PDF page {number}\n\n{text}\n")
        # these text copies help review; the passage builder reads page json instead.
        (source_dir / "review.txt").write_text("".join(review_text), encoding="utf-8")
        (source_dir / "plain-review.txt").write_text("".join(plain_review), encoding="utf-8")
        report["sources"].append({
            **source,
            "sha256": digest,
            "pages_extracted": len(reader.pages),
            "low_text_pages": low_text_pages,
        })
    write_json(output_dir / "extraction-report.json", report)
    # main uses the returned report to print counts; the extracted pages are already on disk.
    return report


def main() -> None:
    # command-line arguments can override the three default input and output paths.
    parser = argparse.ArgumentParser(description="extract local reference PDFs for RAG review")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/sources.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/pdfs")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/extracted")
    args = parser.parse_args()
    try:
        report = extract_sources(args.manifest, args.raw_dir, args.output_dir)
    except (OSError, ValueError, KeyError, pypdf.errors.PdfReadError) as exc:
        parser.exit(1, f"data preparation failed: {exc}\n")
    for source in report["sources"]:
        print(f"{source['source_id']}: {source['pages_extracted']} pages extracted")
    print(f"Review files: {args.output_dir}")


# importing functions in tests should not start a command-line extraction run.
if __name__ == "__main__":
    main()
