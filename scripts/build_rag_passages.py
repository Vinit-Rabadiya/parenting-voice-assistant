# reads extracted page json and selection rules, then prepares source-linked rag passages.
# main writes the returned records to jsonl and review files; embedding happens in a later stage.
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def normalize(text: str) -> str:
    # standardize unicode and collapse whitespace so headings match across pdf line breaks.
    return " ".join(unicodedata.normalize("NFC", text).split())


def select_span(text: str, start: str, end: str | None) -> tuple[str, int, int]:
    # unique anchors avoid accidentally selecting a different activity with a repeated heading.
    if text.count(start) != 1:
        raise ValueError(f"expected one start anchor: {start}")
    first = text.index(start)
    if end is None:
        last = len(text)
    else:
        if text.count(end) != 1:
            raise ValueError(f"expected one end anchor: {end}")
        last = text.index(end)
        if last <= first:
            raise ValueError(f"end anchor precedes start: {start}")
    # include the start heading, exclude the end heading, and return traceable character offsets.
    return text[first:last].strip(), first, last


def build_passages(manifest_path: Path, selections_path: Path, extracted_dir: Path) -> list[dict]:
    # index source metadata by id so each passage can look up its citation information.
    sources = {s["source_id"]: s for s in json.loads(manifest_path.read_text(encoding="utf-8"))["sources"]}
    selections = json.loads(selections_path.read_text(encoding="utf-8"))
    if selections.get("schema_version") != 1:
        raise ValueError("unsupported selections version")
    records = []

    def load_page(source_id: str, number: int) -> tuple[dict, str]:
        # this nested helper reads sources and extracted_dir from the enclosing function.
        page = json.loads((extracted_dir / source_id / f"page-{number:03d}.json").read_text(encoding="utf-8"))
        if (page["source_sha256"] != sources[source_id]["sha256"]
                or page["source_id"] != source_id or page["pdf_page"] != number):
            raise ValueError(f"page provenance mismatch: {source_id} page {number}")
        # reach up's layout text keeps activity blocks together better than its plain text.
        page["extraction_field"] = "layout_text" if source_id == "reach-up-parent-manual-2020" else "text"
        return page, normalize(page[page["extraction_field"]])

    def add(page: dict, text: str, title: str, age: dict, topic: str, routines: list,
            span: list[int], corrections: list | None = None) -> None:
        # append to the enclosing records list; this helper does not write to a database.
        if len(text) < 40 or len(text) > 1800:
            raise ValueError(f"unexpected passage size: {title}")
        source = sources[page["source_id"]]
        # identity follows source/page/title; content_sha256 separately detects text changes.
        identity = f"{source['source_id']}:{page['pdf_page']}:{title}"
        records.append({
            "passage_id": hashlib.sha256(identity.encode()).hexdigest()[:20],
            "source_id": source["source_id"], "source_sha256": source["sha256"],
            "source_title": source["title"], "publisher": source["publisher"],
            "source_url": source["source_url"], "reuse_status": source["reuse_status"],
            "pdf_page": page["pdf_page"], "pdf_page_label": page["pdf_page_label"],
            "title": title, "text": text, "source_age": age,
            "project_scope": {"min_months": 0, "max_months_inclusive": 24},
            "topic": topic, "routines": routines,
            "normalized_page_span": span, "corrections": corrections or [],
            "extraction_field": page["extraction_field"],
            "review_status": "editorially_selected_not_expert_validated",
            "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        })

    def load_page_plain(source_id: str, number: int) -> tuple[dict, str]:
        # like load_page but always uses plain text, needed for sources where layout scrambles columns.
        page = json.loads((extracted_dir / source_id / f"page-{number:03d}.json").read_text(encoding="utf-8"))
        if (page["source_sha256"] != sources[source_id]["sha256"]
                or page["source_id"] != source_id or page["pdf_page"] != number):
            raise ValueError(f"page provenance mismatch: {source_id} page {number}")
        page["extraction_field"] = "text"
        return page, normalize(page["text"])

    if selections.get("ccd_page_2"):
        # the reviewed plain extraction has six play/communication blocks before the age headings.
        page, text = load_page("who-unicef-ccd-cards", 2)
        first = text.index("PLAY ")
        last = text.index("NEWBORN,")
        starts = list(re.finditer(r"\bPLAY ", text[first:last]))
        if len(starts) != 6:
            raise ValueError("expected six CCD age columns")
        # match the six visually reviewed columns in order and keep the one-week boundary in days.
        ages = [
            {"label": "birth up to 1 week", "min_days": 0, "max_days_exclusive": 7},
            {"label": "1 week up to 6 months", "min_days": 7, "max_months_exclusive": 6},
            {"label": "6 months up to 9 months", "min_months": 6, "max_months_exclusive": 9},
            {"label": "9 months up to 12 months", "min_months": 9, "max_months_exclusive": 12},
            {"label": "12 months up to 2 years", "min_months": 12, "max_months_exclusive": 24},
            {"label": "2 years and older", "min_months": 24, "max_months_exclusive": None},
        ]
        for i, match in enumerate(starts):
            # match positions are relative to the sliced text, so add first to get page offsets.
            begin = first + match.start()
            end = first + starts[i + 1].start() if i + 1 < len(starts) else last
            block = text[begin:end]
            if block.count("COMMUNICATE") != 1:
                raise ValueError("missing CCD communication section")
            # make two passages per age column instead of mixing play and communication text.
            split = block.index("COMMUNICATE")
            for topic, a, b in [("play", begin, begin + split), ("communication", begin + split, end)]:
                passage = text[a:b].strip()
                corrections = []
                # record each known extraction repair so tests can reconstruct the final text.
                for original, replacement in [("T alk", "Talk"), ("T ell", "Tell"), ("T each", "Teach")]:
                    if original in passage:
                        passage = passage.replace(original, replacement)
                        corrections.append({"from": original, "to": replacement})
                add(page, passage, f"{ages[i]['label']}: {topic}", ages[i], topic,
                    ["play"] if topic == "play" else [], [a, b], corrections)

    if selections.get("ccd_page_3"):
        # page 3 has counsellor-facing problem guidance: each "If..." block is a separate passage.
        page, text = load_page("who-unicef-ccd-cards", 3)
        # these are the six distinct problem scenarios on the page.
        problem_blocks = [
            ("If the mother does not breastfeed",
             "If caregivers do not know what the child does to play or communicate",
             "not breastfeeding: responsive feeding", {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}, "responsive_caregiving", ["feeding"]),
            ("If caregivers do not know what the child does to play or communicate",
             "If caregivers feel too burdened or stressed",
             "caregivers unsure how child plays or communicates", {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}, "responsive_caregiving", []),
            ("If caregivers feel too burdened or stressed to play and communicate with the child",
             "If caregivers feel that they do not have time",
             "caregivers feel stressed or burdened", {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}, "responsive_caregiving", []),
            ("If caregivers feel that they do not have time to play and communicate with the child",
             "If caregivers have no toys",
             "caregivers have no time to play", {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}, "responsive_caregiving", []),
            ("If caregivers have no toys for the child to play with",
             "If the child is not responding, or seems slow",
             "no toys available", {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}, "play", []),
            ("If the child is not responding, or seems slow",
             "If the mother or father has to leave",
             "child not responding or seems slow", {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}, "development", []),
        ]
        for start, end, title, age, topic, routines in problem_blocks:
            passage, first, last = select_span(text, start, end)
            add(page, passage, title, age, topic, routines, [first, last])

    for selection in selections.get("reach_up_general", []):
        # general caregiving guidance from pages 33-34: no age band, applies across 0-24 months.
        page, text = load_page_plain("reach-up-parent-manual-2020", selection["page"])
        passage, first, last = select_span(text, selection["start"], selection.get("end"))
        age = {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None}
        add(page, passage, selection["title"], age, selection["topic"], selection["routines"], [first, last])

    for selection in selections.get("reach_up_play", []):
        # play activity pages 7-22 use plain text; layout scrambles the two-column table layout.
        # the numbered activity anchors (1. Soothe baby, 2. Let baby know mummy, etc.) are unique
        # within each page. continuation pages (8,10,12...) do not repeat the age heading.
        page, text = load_page_plain("reach-up-parent-manual-2020", selection["page"])
        low, high = selection["age"]
        if not (isinstance(low, int) and isinstance(high, int) and 0 <= low <= 24 and low < high):
            raise ValueError("invalid selected age interval")
        passage, first, last = select_span(text, selection["start"], selection.get("end"))
        if "Play and language activities" in passage:
            raise ValueError(f"page header leaked into passage: {selection['start']}")
        add(page, passage, selection["start"],
            {"label": f"{low}-{high - 1} months", "min_months": low, "max_months_exclusive": high},
            selection["topic"], selection["routines"], [first, last])

    if selections.get("kenya_milestones"):
        # page 27 (pdf label 25): developmental milestones table — each age band is one passage.
        page, text = load_page("kenya-moh-mch-handbook", 27)
        milestone_bands = [
            ("Social smile/follows a colourful object dangled before their eyes",
             "Holds the head upright",
             "Developmental milestone: 0-2 months",
             {"label": "0-2 months", "min_months": 0, "max_months_exclusive": 2}),
            ("Holds the head upright / follows the object or face with their eyes / turns the head or responds in any other way to sound / smiles when you speak",
             "Rolls over",
             "Developmental milestone: 2-4 months",
             {"label": "2-4 months", "min_months": 2, "max_months_exclusive": 4}),
            ("Rolls over / reaches for and grasps objects with hand / takes objects to her mouth / babbles (makes sounds)",
             "Sits without support",
             "Developmental milestone: 4-6 months",
             {"label": "4-6 months", "min_months": 4, "max_months_exclusive": 6}),
            ("Sits without support / moves object from one hand to the other/ repeats syllables (bababa, mamama)",
             "Takes steps with support",
             "Developmental milestone: 6-9 months",
             {"label": "6-9 months", "min_months": 6, "max_months_exclusive": 9}),
            ("Takes steps with support / picks up small object or string with 2 fingers / says 2-3 words / imitates simple gestures (claps hands, bye)",
             "Walks without support",
             "Developmental milestone: 9-12 months",
             {"label": "9-12 months", "min_months": 9, "max_months_exclusive": 12}),
            ("Walks without support / drinks from a cup / says 7-10 words / points to some body parts on request",
             "Kicks a ball",
             "Developmental milestone: 12-18 months",
             {"label": "12-18 months", "min_months": 12, "max_months_exclusive": 18}),
            ("Kicks a ball / builds tower with 3 blocks or small boxes / points at pictures on request / speaks in short sentences",
             "Jumps/ undresses and dresses",
             "Developmental milestone: 18-24 months",
             {"label": "18-24 months", "min_months": 18, "max_months_exclusive": 24}),
            ("Jumps/ undresses and dresses themselves / says name, tells short story/ interested in playing with other children",
             "Refer for further assessment",
             "Developmental milestone: 24 months and older",
             {"label": "24 months and older", "min_months": 24, "max_months_exclusive": None}),
        ]
        for start, end, title, age in milestone_bands:
            passage, first, last = select_span(text, start, end)
            add(page, passage, title, age, "development", [], [first, last])

    if selections.get("kenya_feeding"):
        # page 43 (pdf label 41): breastfeeding and complementary feeding guidance.
        page, text = load_page("kenya-moh-mch-handbook", 43)
        feeding_sections = [
            ("BREASTFEEDING",
             "1 WEEK UP TO 6 MONTHS",
             "Breastfeeding: newborn up to 1 week",
             {"label": "birth up to 1 week", "min_days": 0, "max_days_exclusive": 7},
             ["feeding"]),
            ("1 WEEK UP TO 6 MONTHS",
             "Counsel the caregiver on feeding recommendations",
             "Breastfeeding: 1 week up to 6 months",
             {"label": "1 week up to 6 months", "min_days": 7, "max_months_exclusive": 6},
             ["feeding"]),
            ("COMPLEMENTARY FEEDING",
             "Non-breastfed baby",
             "Complementary feeding: 6 months to 2 years",
             {"label": "6 months to 2 years", "min_months": 6, "max_months_exclusive": 24},
             ["feeding"]),
            ("Feeding sick children",
             "See page 18",
             "Feeding sick children and during recovery",
             {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None},
             ["feeding"]),
        ]
        for start, end, title, age, routines in feeding_sections:
            passage, first, last = select_span(text, start, end)
            add(page, passage, title, age, "feeding", routines, [first, last])

    if selections.get("kenya_danger_signs"):
        # page 45 (pdf label 43): when to return immediately — danger signs for sick children.
        page, text = load_page("kenya-moh-mch-handbook", 45)
        start = "BRING ANY SICK CHILD IF:"
        end = "Recommendations for - Care for Child Development"
        passage, first, last = select_span(text, start, end)
        add(page, passage,
            "When to seek care immediately: danger signs",
            {"label": "0-24 months", "min_months": 0, "max_months_exclusive": None},
            "safety", [], [first, last])
        # each rule supplies the page, activity headings, and editorial age/routine labels.
    for selection in selections["reach_up"]:
        page, text = load_page("reach-up-parent-manual-2020", selection["page"])
        low, high = selection["age"]
        if not (isinstance(low, int) and isinstance(high, int) and 0 <= low <= 24 and low < high):
            raise ValueError("invalid selected age interval")
        # an exclusive upper bound of nine corresponds to the source heading six to eight months.
        heading = f"FOR CHILDREN AGES {low}-{high - 1} MONTHS"
        if heading not in text:
            raise ValueError(f"age heading mismatch on page {selection['page']}")
        # unpack the selected activity and its offsets, then attach metadata through add.
        passage, first, last = select_span(text, selection["start"], selection["end"])
        if "PLAY AND LANGUAGE ACTIVITIES" in passage or "FOR CHILDREN AGES" in passage:
            raise ValueError(f"page header leaked into passage: {selection['start']}")
        add(page, passage, selection["start"],
            {"label": f"{low}-{high - 1} months", "min_months": low, "max_months_exclusive": high},
            selection["topic"], selection["routines"], [first, last])
    # sets detect repeated identities or exact text; they do not detect paraphrased duplicates.
    if len({p["passage_id"] for p in records}) != len(records):
        raise ValueError("duplicate passage ids")
    if len({p["content_sha256"] for p in records}) != len(records):
        raise ValueError("duplicate passage content; review the selections")
    # main receives the complete list only after selection and duplicate checks succeed.
    return records


def main() -> None:
    # keep command-line paths and disk output here so tests can call build_passages directly.
    parser = argparse.ArgumentParser(description="build explicitly selected age-aware RAG passages")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/sources.json")
    parser.add_argument("--selections", type=Path, default=ROOT / "data/passage-selections.json")
    parser.add_argument("--extracted-dir", type=Path, default=ROOT / "data/processed/extracted")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/rag")
    args = parser.parse_args()
    try:
        records = build_passages(args.manifest, args.selections, args.extracted_dir)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        # jsonl stores one passage dictionary per line for later indexing.
        (args.output_dir / "passages.jsonl").write_text(
            "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in records), encoding="utf-8")
        # render the same records for reading; this markdown is not an input to indexing.
        (args.output_dir / "passages-review.md").write_text("\n\n".join(
            f"## {p['passage_id']} — {p['title']}\n\n"
            f"Source: {p['source_id']}, PDF page {p['pdf_page']}\n\n"
            f"Age: {p['source_age']['label']} | Routines: {', '.join(p['routines']) or 'unspecified'}\n\n"
            f"{p['text']}" for p in records) + "\n", encoding="utf-8")
        # record which input configurations produced this corpus and how many passages it has.
        report = {
            "schema_version": 1,
            "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "selections_sha256": hashlib.sha256(args.selections.read_bytes()).hexdigest(),
            "passage_count": len(records),
            "sources": {source_id: {
                "passage_count": sum(p["source_id"] == source_id for p in records),
                "selected_pdf_pages": sorted({p["pdf_page"] for p in records if p["source_id"] == source_id}),
            } for source_id in sorted({p["source_id"] for p in records})},
            "review_status": "selected subset; not comprehensive or expert validated",
            "age_policy": "intersect source_age with project_scope; upper source bounds are exclusive",
            "index_built": False,
        }
        (args.output_dir / "preparation-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"passage preparation failed: {exc}\n")
    print(f"Prepared {len(records)} passages in {args.output_dir}")


# run the command only when executed directly, not when tests import its functions.
if __name__ == "__main__":
    main()
