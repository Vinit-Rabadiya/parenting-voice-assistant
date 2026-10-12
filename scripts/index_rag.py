# reads prepared passages for indexing into qdrant.
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import Document, PointStruct

from backend.core.config import PROJECT_ROOT


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

            # include the input line number when reporting invalid source or age metadata.
            try:
                validate_source_metadata(passage)
                validate_age_metadata(passage)
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

    # project_scope limits our application independently of the document's age range.
    scope = passage.get("project_scope")
    if not isinstance(scope, dict):
        raise ValueError("project_scope must be an object.")

    expected_scope = {"min_months": 0, "max_months_inclusive": 24}
    if set(scope) != set(expected_scope):
        raise ValueError("project_scope must define the project's month boundaries.")

    for field, expected in expected_scope.items():
        if type(scope[field]) is not int or scope[field] != expected:
            raise ValueError(f"project_scope.{field} must be {expected}.")


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


def main() -> None:
    passages_path = PROJECT_ROOT / "data/processed/rag/passages.jsonl"

    try:
        passages = load_passages(passages_path)
        # these point objects exist only in python memory until an upload stores them in qdrant.
        points = [build_point(passage) for passage in passages]
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Passage preparation failed: {exc}") from None

    print(f"Loaded passages: {len(passages)}")
    print(f"Prepared Qdrant points: {len(points)}")
    print("No points uploaded.")


if __name__ == "__main__":
    main()
