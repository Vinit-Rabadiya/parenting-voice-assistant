# reads prepared passages for indexing into qdrant.
import json

from backend.core.config import PROJECT_ROOT


def main() -> None:
    passages_path = PROJECT_ROOT / "data/processed/rag/passages.jsonl"

    # select the feeding activity we already reviewed from reach up page 41.
    matches = []

    with passages_path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue

            passage = json.loads(line)

            if (
                passage["source_id"] == "reach-up-parent-manual-2020"
                and passage["pdf_page"] == 41
                and passage["title"] == "Talk with baby during feeding time"
            ):
                matches.append(passage)

    if len(matches) != 1:
        raise SystemExit("Expected exactly one matching feeding passage.")

    passage = matches[0]
    print("Passage ID:", passage["passage_id"])
    print("Text:", passage["text"])
    print("Age:", passage["source_age"])


if __name__ == "__main__":
    main()