# RAG data preparation

This is the first selected reference corpus, not a complete knowledge base or a trained model.
It contains 33 editorially selected passages: 12 WHO/UNICEF counselling-card passages and
21 Reach Up activity passages. Selection and extraction have been checked by the coding
agent; developmental appropriateness has not been evaluated by an ECD specialist.

## Reproduce on Windows

From the repository root, with the three PDFs present under `data/raw/pdfs/`:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\venv\Scripts\python.exe scripts/prepare_rag_data.py
.\venv\Scripts\python.exe scripts/build_rag_passages.py
.\venv\Scripts\python.exe -m pytest tests/test_rag_data.py
```

Both scripts resolve their default paths from the repository root, independently of the
terminal's working directory. The tests also use synthetic inputs; the final local corpus
test skips on CI when the source documents/extractions are unavailable.

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

## Age semantics

Source age ranges and project scope are separate. Retrieval must intersect both.

- Reach Up `6-8 months` means completed ages 6, 7, and 8: `[6, 9)` months.
- CCD `birth up to 1 week` uses `[0, 7)` days; the next band begins at day 7 and ends
  before six months. Do not round both bands to `0 months`.
- The source range `24-26 months` remains `[24, 27)`. CCD `2 years and older` remains
  open-ended. The project's upper age is separately recorded as 24 months inclusive.
  These passages must not match younger children or extend project support beyond 24 months.
- Future profile handling should calculate completed calendar months and exact age in days
  from birth date; it should not use a fixed 30-day month. Clarify whether the final product
  includes the full completed 24th month when defining profile eligibility.
- `routines: []` means the selected passage has no specific routine annotation, not that
  every routine is supported. Topics/routines are editorial labels, not clinical milestones.

## Source review decisions and coverage gaps

| Source/pages | Current treatment |
| --- | --- |
| CCD page 1 | Cover; not selected. |
| CCD page 2 | All six columns extracted as 12 passages; preserve age limits. |
| CCD page 3 | Counsellor-facing problem guidance; extracted, pending passage selection. |
| CCD page 4 | Rotated counselling checklist; pending structured review. |
| Reach Up pages 1–31 | Front matter and programme tables; repeated activities are not separately indexed. |
| Reach Up pages 32–35 | General parent guidance; extracted, pending selection. |
| Reach Up page 36 | Section divider; not selected. |
| Reach Up pages 37–52 | Selected individual activities, primarily communication; other activities remain unselected. |
| Reach Up pages 53–64 | Extracted; unselected. Page 53 overlaps the 24-month boundary; later age groups exceed scope. |
| Kenya handbook, all pages | Extracted only. Page 27 (PDF label 25) has a milestone table adjacent to clinical assessment content; requires table-specific modelling before inclusion. |

The current subset covers each infant age band but is uneven across routines. It is not
comprehensive feeding, bathing, sleep, soothing, motor-development, or milestone guidance.
The local parenting CSV is not part of this RAG preparation; its training provenance remains
a separate question. Expert evaluation, held-out caregiver questions, retrieval indexing,
age-filter implementation, ranking evaluation, and LLM response generation are next stages.

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
