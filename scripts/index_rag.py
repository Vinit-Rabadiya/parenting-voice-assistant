import argparse
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import Document, PointStruct

from backend.core.config import PROJECT_ROOT, settings
from scripts.create_qdrant_collection import ensure_age_indexes


def load_passages(path: Path) -> list[dict]:
    passages = []
    seen_ids = set()

    # read one json record per line and preserve its original text and metadata.
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue

            try:
                passage = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON on line {line_number}.") from None

            if not isinstance(passage, dict):
                raise ValueError(f"Line {line_number} must contain a JSON object.")

            # these fields are required to identify and embed each passage.
            for field in ("passage_id", "text"):
                value = passage.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Line {line_number} requires a nonempty {field}.")

            # include the input line number when reporting invalid passage metadata.
            try:
                validate_source_metadata(passage)
                validate_age_metadata(passage)
                validate_routine_metadata(passage)
            except ValueError as exc:
                raise ValueError(f"Line {line_number}: {exc}") from None

            # reject repeated ids before they can overwrite each other during indexing.
            passage_id = passage["passage_id"]
            if passage_id in seen_ids:
                raise ValueError(f"Duplicate passage ID on line {line_number}.")

            seen_ids.add(passage_id)
            passages.append(passage)

    if not passages:
        raise ValueError("The passage file contains no records.")

    return passages


def validate_source_metadata(passage: dict) -> None:
    # metadata describes where the passage came from so results can include citations.
    for field in ("source_id", "source_title", "source_url"):
        value = passage.get(field)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be nonempty text.")

    if passage.get("source_format") == "web_summary":
        if passage.get("pdf_page") is not None:
            raise ValueError("Web references must not invent a PDF page.")
        if not isinstance(passage.get("source_section"), str) or not passage["source_section"].strip():
            raise ValueError("Web references require source_section.")
        return
    # pdf_page is the physical page number used to locate the original passage.
    page = passage.get("pdf_page")
    if type(page) is not int or page < 1:
        raise ValueError("pdf_page must be a positive integer.")


def validate_age_metadata(passage: dict) -> None:
    # source_age describes the ages assigned to this activity by its document.
    age = passage.get("source_age")
    if not isinstance(age, dict):
        raise ValueError("source_age must be an object.")

    label = age.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("source_age.label must be nonempty text.")

    # identify the boundary format without treating the readable label as a boundary.
    boundaries = set(age) - {"label"}
    supported = (
        {"min_months", "max_months_exclusive"},
        {"min_days", "max_days_exclusive"},
        {"min_days", "max_months_exclusive"},
    )
    if boundaries not in supported:
        raise ValueError("source_age uses an unsupported boundary format.")

    # exact integer checks reject booleans, decimal numbers, and numeric strings.
    for field in boundaries:
        value = age[field]

        # a null upper bound means the source range is open-ended.
        if field.startswith("max_") and value is None:
            continue

        if type(value) is not int or value < 0:
            raise ValueError(f"source_age.{field} must be a non-negative integer.")

    # compare bounds directly only when both use the same unit.
    for unit in ("days", "months"):
        lower = age.get(f"min_{unit}")
        upper = age.get(f"max_{unit}_exclusive")

        if lower is not None and upper is not None and upper <= lower:
            raise ValueError(f"source_age upper {unit} must exceed lower {unit}.")

    # the current mixed-unit format represents the reviewed one-week-to-six-month band.
    if boundaries == {"min_days", "max_months_exclusive"}:
        if age["min_days"] != 7 or age["max_months_exclusive"] != 6:
            raise ValueError("The supported mixed-unit range is 7 days to under 6 months.")

    # project_scope limits the application independently of the document's age range.
    scope = passage.get("project_scope")
    if not isinstance(scope, dict):
        raise ValueError("project_scope must be an object.")

    expected_scope = {"min_months": 0, "max_months_inclusive": 24}
    if set(scope) != set(expected_scope):
        raise ValueError("project_scope must define the project's month boundaries.")

    for field, expected in expected_scope.items():
        if type(scope[field]) is not int or scope[field] != expected:
            raise ValueError(f"project_scope.{field} must be {expected}.")


def validate_routine_metadata(passage: dict) -> None:
    # routines are activity labels used later to filter or rank retrieved passages.
    routines = passage.get("routines")
    if not isinstance(routines, list):
        raise ValueError("routines must be a list.")

    # an empty list means no specific routine was annotated, not that every routine applies.
    for routine in routines:
        if not isinstance(routine, str) or not routine.strip():
            raise ValueError("Each routine must be nonempty text.")

        # consistent casing and spacing prevent accidental label mismatches.
        if routine != routine.strip().lower():
            raise ValueError("Routine labels must be lowercase without surrounding spaces.")

    # a set removes duplicates; a shorter set means a label appeared more than once.
    if len(routines) != len(set(routines)):
        raise ValueError("Routine labels must not repeat.")


def validate_source_references(passages: list[dict], manifest_path: Path) -> None:
    # The manifest is the versioned inventory of documents, page counts, and file fingerprints.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int:
        raise ValueError("Source manifest must be an object with an integer schema_version.")
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported source manifest version.")
    entries = manifest.get("sources")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Source manifest must contain a nonempty sources list.")

    # build a lookup once so every passage can find its source without rereading the file.
    sources = {}
    for position, source in enumerate(entries, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"Manifest source {position} must be an object.")
        for field in ("source_id", "title", "source_url", "sha256"):
            value = source.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Manifest source {position} requires nonempty {field}.")

        # sha256 is a 64-character hexadecimal fingerprint, not proof of factual accuracy.
        digest = source["sha256"]
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"Manifest source {position} has an invalid sha256 fingerprint.")
        page_count = source.get("expected_pages")
        if source.get("source_format") != "web_summary" and (type(page_count) is not int or page_count < 1):
            raise ValueError(f"Manifest source {position} requires a positive integer expected_pages.")

        source_id = source["source_id"]
        if source_id in sources:
            raise ValueError(f"Duplicate source ID in manifest: {source_id}")
        sources[source_id] = source

    # these passages have already passed the individual field checks in load_passages.
    for passage in passages:
        passage_id = passage["passage_id"]
        source = sources.get(passage["source_id"])
        if source is None:
            raise ValueError(f"Passage {passage_id} refers to an unknown source.")

        # pair passage field names with their corresponding manifest field names.
        field_pairs = (
            ("source_title", "title"),
            ("source_url", "source_url"),
            ("source_sha256", "sha256"),
        )
        for passage_field, source_field in field_pairs:
            if passage.get(passage_field) != source[source_field]:
                raise ValueError(
                    f"Passage {passage_id}: {passage_field} does not match the manifest."
                )

        # positive page numbers were checked earlier; now enforce the document's page limit.
        if source.get("source_format") == "web_summary":
            if passage.get("source_format") != "web_summary" or passage.get("pdf_page") is not None:
                raise ValueError(f"Passage {passage_id}: source format does not match the manifest.")
            if passage.get("source_section") not in source.get("sections", []):
                raise ValueError(f"Passage {passage_id}: unknown source section.")
        elif passage.get("source_format") == "web_summary" or passage["pdf_page"] > source["expected_pages"]:
            raise ValueError(f"Passage {passage_id} refers to a page beyond the source document.")


def build_point(passage: dict) -> PointStruct:
    # a point is one qdrant record: an id, a vector, and a payload; one passage becomes one point.
    # a collection groups these points under a shared vector size and similarity metric.
    # derive the same qdrant id whenever this passage is indexed again.
    point_id = str(
        uuid5(
            NAMESPACE_URL,
            f"parenting-voice-assistant:passage:{passage['passage_id']}",
        )
    )

    # an embedding is a numerical vector representing text meaning for similarity search.
    # document holds text and model instructions, not the 384 numbers the model will generate.
    # cloud inference generates those numbers when submitted through an inference-enabled client.
    embedding_input = Document(
        text=passage["text"],
        model="sentence-transformers/all-minilm-l6-v2",
    )

    # payload is the readable text and metadata returned with a match, including age and source.
    return PointStruct(
        id=point_id,
        vector=embedding_input,
        payload=passage,
    )


def upload_points(points: list[PointStruct], collection_name: str = "caregiver_guidance_minilm_v1") -> int:
    # requires valid connection credentials from the root environment.
    url = (settings.QDRANT_URL or "").strip()
    api_key = (settings.QDRANT_API_KEY or "").strip()
    if not url or not api_key:
        raise ValueError("Set QDRANT_URL and QDRANT_API_KEY in the root .env.")

    client = QdrantClient(
        url=url,
        port=443,
        api_key=api_key,
        cloud_inference=True,
        timeout=30,
    )
    try:
        if not client.collection_exists(collection_name):
            raise ValueError(
                f"Collection '{collection_name}' not found. Run scripts/create_qdrant_collection.py first."
            )
        ensure_age_indexes(client, collection_name)
        # upload batch to qdrant with cloud inference for embeddings
        client.upsert(collection_name=collection_name, points=points)
        return len(points)
    finally:
        client.close()


def mark_index_built(report_path: Path) -> None:
    # record that this corpus version has been uploaded so the report stays in sync.
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["index_built"] = True
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and optionally upload RAG passages to Qdrant.")
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the prepared points to the Qdrant Cloud collection.",
    )
    parser.add_argument("--passages", type=Path, default=PROJECT_ROOT / "data/processed/rag/passages.jsonl")
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/sources.json")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "data/processed/rag/preparation-report.json")
    parser.add_argument("--collection", default=settings.QDRANT_COLLECTION)
    parser.add_argument("--allow-candidate-upload", action="store_true",
                        help="Allow a candidate corpus only into a separate staging collection.")
    args = parser.parse_args()

    passages_path = args.passages
    report_path = args.report

    try:
        passages = load_passages(passages_path)
        # cross-check the whole corpus against the source inventory before constructing points.
        validate_source_references(passages, args.manifest)
        candidate = any(p.get("review_status") == "candidate_not_expert_validated" for p in passages)
        if args.upload and candidate and (not args.allow_candidate_upload or args.collection == settings.QDRANT_COLLECTION):
            raise ValueError("Candidate passages require --allow-candidate-upload and a separate staging collection.")
        # these point objects exist only in python memory until an upload stores them in qdrant.
        points = [build_point(passage) for passage in passages]
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Passage preparation failed: {exc}") from None

    print(f"Loaded passages: {len(passages)}")
    print(f"Prepared Qdrant points: {len(points)}")

    if args.upload:
        try:
            uploaded_count = upload_points(points, args.collection)
            print(f"Successfully uploaded {uploaded_count} points to Qdrant Cloud.")
            # update the report so the index_built flag reflects the current state.
            if report_path.exists():
                mark_index_built(report_path)
                print(f"Updated {report_path.name}: index_built = true")
        except Exception as exc:
            raise SystemExit(f"Upload failed: {exc}") from None
    else:
        print("Dry run complete. Pass --upload to store points in Qdrant Cloud.")


if __name__ == "__main__":
    main()

