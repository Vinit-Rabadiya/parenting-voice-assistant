# RAG data preparation

The selected reference corpus supports retrieval, not model training. The current prepared
corpus contains 106 editorially selected passages: 18 WHO/UNICEF counselling-card passages,
75 Reach Up passages, and 13 Kenya handbook passages. Selection and extraction checks do
not constitute expert validation of developmental appropriateness.

## Reproduce on Windows

From the repository root, with the three PDFs present under `data/raw/pdfs/`:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\venv\Scripts\python.exe -m scripts.prepare_rag_data
.\venv\Scripts\python.exe -m scripts.build_rag_passages
.\venv\Scripts\python.exe -m pytest tests/test_rag_data.py
```

Both scripts resolve their default paths from the repository root, independently of the
terminal's working directory. Source PDFs must match the fingerprints in `sources.json`.

## Verify real-corpus age filtering

Install the test dependencies with `pip install -r requirements-dev.txt`, then run:

```powershell
.\venv\Scripts\python.exe -m pytest --require-corpus -ra tests/test_retrieval_corpus.py tests/test_age_filter.py tests/test_caregiver_data.py tests/test_evidence_gate.py tests/test_corpus_requirement.py
```

`--require-corpus` stops the run with an error if `data/processed/rag/passages.jsonl` is
missing. Invalid passage metadata or source references also fail the integration tests.
The option checks file availability, not corpus freshness; regenerate from the source
PDFs and versioned selection rules when preparing release evidence.

The real-corpus tests load the prepared payloads into in-memory Qdrant. They check six
days, seven days, the day before six months, exactly six months, and the second birthday.
Coaching API checks also reject profiles the day after the second birthday and at thirty
months, before retrieval, generation, or interaction storage.

Fixed synthetic vectors isolate age filtering from semantic ranking. Authentication,
generation, and persistence are isolated; these tests do not access cloud services or
measure answer quality, embedding accuracy, or latency.

Normal `pytest` runs skip the real-corpus checks when the generated passage file is absent.
CI does not obtain the source PDFs or prepare the corpus, so a green CI result alone is
not evidence that these checks ran. Use the explicit command above and retain the test
summary, including skipped tests (`-ra`), with the PR verification record.

## Date-based retrieval evaluation

`data/evaluation/retrieval-queries.jsonl` contains development questions and passage labels.
Each case specifies a synthetic `date_of_birth` and fixed `evaluation_date` in `YYYY-MM-DD`
format. The runner calculates exact days and completed calendar months with the same age
helpers used by profiles. It rejects missing or invalid dates, out-of-scope ages, and
precomputed age fields rather than silently falling back to approximate month conversion.
The dates are fixed so a case does not change age when the evaluation is rerun later.

For example, birth on `2026-04-20` evaluated on `2026-10-20` means 183 days and six
completed months. Birth on `2026-04-21` means five completed months, even if its display
age rounds to `6.0`. Only the completed month count is used for month-bound eligibility.

Offline runner checks, without Qdrant network requests:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_retrieval_evaluation.py
```

Running `python -m scripts.evaluate_retrieval` queries the configured live Qdrant collection
and overwrites `data/evaluation/retrieval-results.json`. New reports use schema version 2
and record both input dates, exact days, completed months, and rounded display months.
Previously recorded results remain historical evidence until a new run replaces them;
changing case inputs does not update old scores. The original 12 questions and labels are
not a held-out evaluation set, and their labels need review against the current corpus
before threshold calibration or claims about retrieval accuracy.

## Files and data flow

```text
data/sources.json + data/raw/pdfs/*.pdf
  -> scripts/prepare_rag_data.py
  -> data/processed/extracted/<source-id>/page-NNN.json
  -> plain-review.txt + review.txt + extraction-report.json

extracted pages + data/passage-selections.json
  -> scripts/build_rag_passages.py
  -> data/processed/rag/passages.jsonl
  -> passages-review.md + preparation-report.json
```

- `sources.json` identifies the exact local files using SHA-256 fingerprints. A changed
  PDF stops extraction rather than silently applying old page selections to new content.
  A publication URL is not proof that its current download is byte-identical to the local file.
- Extraction retains plain text and layout text for **all 116 pages**. They are review
  artifacts, not automatically approved retrieval passages. Low-text pages are flagged;
  OCR is not implemented. Layout extraction warns about rotated text in these sources.
  Compare both views with the original page where tables/rotation matter.
- `passage-selections.json` selects individual Reach Up activities using unique heading
  anchors. These operate on layout text because plain extraction reorders activity blocks.
- The CCD page-2 parser maps six visually checked columns to six source age bands and
  separates play from communication. Known split-letter extraction artifacts (`T alk`,
  `T ell`, `T each`) have explicit correction records. No blanket lowercasing or removal
  of punctuation is applied.
- Every passage retains source identity, fingerprint, PDF page, embedded PDF page label,
  normalized source-text offsets, extraction field, original age band, topic, and routines.
  PDF page labels may simply equal physical page numbers; they are not guaranteed to be
  the printed folio. Use `pdf_page` for opening the source.
- `passages.jsonl` is JSON Lines: one independently readable JSON record per line.
  `passages-review.md` is the easier human-readable version.
- Stable IDs identify source/page/title; a separate content fingerprint records the
  actual text. Exact duplicates fail preparation. Related ideas across sources are retained.

Raw PDFs, raw datasets, extracted text, and generated passages stay git-ignored. Metadata,
selection rules, scripts, and documentation are versionable. No download happens in either script.

## From passages to vector retrieval

`scripts.index_rag` uses `sentence-transformers/all-minilm-l6-v2` through Qdrant Cloud
inference. Qdrant stores vectors with the original passage text, source metadata, and age
boundaries. The collection name is configured by `QDRANT_COLLECTION` for live retrieval.
Source IDs and page numbers support citations; similarity alone does not establish suitability.

Before candidate selection, Qdrant filters the original `source_age` day and month fields.
Integer indexes cover `min_days`, `max_days_exclusive`, `min_months`, and
`max_months_exclusive`. Python validation additionally rejects unsupported or malformed age
metadata. Collection setup preserves existing data and ensures these indexes:

```powershell
.\venv\Scripts\python.exe -m scripts.create_qdrant_collection
```

This command changes the configured Qdrant collection; it is not required for the local tests.

## Age semantics

Source age ranges and project scope are separate. Retrieval must intersect both.

- Reach Up `6-8 months` means completed ages 6, 7, and 8: `[6, 9)` months.
- CCD `birth up to 1 week` uses `[0, 7)` days; the next band begins at day 7 and ends
  before six months. Do not round both bands to `0 months`.
- The source range `24-26 months` remains `[24, 27)`. CCD `2 years and older` remains
  open-ended. Coaching is supported from birth through the calendar second birthday,
  inclusive. The following day is out of scope; the full completed 24th month is not included.
- The backend derives completed calendar months and exact days from the stored birth date.
  Live coaching uses days for day boundaries and completed months for month boundaries,
  not rounded display age or a fixed month-to-day conversion. Older profiles remain
  accessible for management, but the coaching API blocks out-of-scope requests before search.
- `routines: []` means the selected passage has no specific routine annotation, not that
  every routine is supported. Topics/routines are editorial labels, not clinical milestones.

## Source review decisions and coverage gaps

| Source/pages | Current treatment |
| --- | --- |
| CCD page 1 | Cover; not selected. |
| CCD page 2 | All six columns extracted as 12 passages; preserve age limits. |
| CCD page 3 | Six selected passages; counsellor-facing context still requires relevance review. |
| CCD page 4 | Rotated counselling checklist; pending structured review. |
| Reach Up pages 1–31 | Selected activities from pages 7–22; other content remains unselected. |
| Reach Up pages 32–35 | Seven selected general parent-guidance passages. |
| Reach Up page 36 | Section divider; not selected. |
| Reach Up pages 37–52 | Selected individual activities, primarily communication; other activities remain unselected. |
| Reach Up pages 53–64 | Extracted; unselected. Page 53 overlaps the 24-month boundary; later age groups exceed scope. |
| Kenya handbook | Thirteen selected passages from PDF pages 27, 43, and 45; neighbouring clinical content is outside the coaching scope. |

The current subset covers each infant age band but is uneven across routines. It is not
comprehensive feeding, bathing, sleep, soothing, motor-development, or milestone guidance.
The local parenting CSV is not part of this RAG preparation; its training provenance remains
a separate question. Expert evaluation, held-out caregiver questions, and semantic ranking
evaluation remain separate from the implemented indexing, age filtering, and LLM generation.

## Attribution and reuse metadata

Reach Up states CC BY-NC-SA 4.0 in PDF pages 2 and 31, with attribution to The University
of the West Indies. Source metadata preserves that statement. Reuse terms for the other
documents have not been established here. The public repository contains selection rules,
not copies of the source corpus. Do not describe extracted content as original project authorship.

## Reading the library documentation

See [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
Start with `extract_text()` and `extraction_mode="layout"`, then read “Why Text Extraction
is hard.” The distinction explains why page text is preserved for review before selecting
passages: a PDF describes positioned drawing/text operations, not reliable paragraph or
table structure.
