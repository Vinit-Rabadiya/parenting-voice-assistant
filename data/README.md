# RAG data preparation

The selected reference corpus supports retrieval, not model training. The current prepared
corpus contains 106 editorially selected passages: 18 WHO/UNICEF counselling-card passages,
75 Reach Up passages, and 13 Kenya handbook passages. Selection and extraction checks do
not constitute expert validation of developmental appropriateness.

## Expanded reference candidates

`reference-expansion.json` adds short editorial summaries from UNICEF Parenting
and NHS guidance, checked on 22 October 2026. It is a candidate source pack,
not a clinical validation record or a snapshot of the publisher's complete page.
The original three-PDF corpus and live collection remain unchanged.

The pack contains 47 candidate passages from 12 additional source pages:
development at 2, 4, 6, 9, 12, 18, and 24 months; everyday interaction;
feeding; bathing; and sleep. Domains include cognitive, language, social-emotional,
gross/fine motor, nutrition, responsive caregiving, and safety.
Immunisation sources are listed as pending, not included in retrieval. Official
country-specific schedule reconciliation and professional review remain necessary.

Prepare and inspect a separate candidate corpus without network calls:

```powershell
.\venv\Scripts\python.exe -m scripts.build_reference_expansion
.\venv\Scripts\python.exe -m scripts.index_rag --passages data/processed/expanded/passages.jsonl --manifest data/processed/expanded/sources.json --report data/processed/expanded/preparation-report.json
```

With the current 106-passage base this produces 153 passages. It does not download
sources, call a model, obtain embeddings, upload points, or change the application
collection. The generated report records counts, domains, coverage, and fingerprints.
The web-source fingerprint identifies the canonical editorial source entry,
**not** downloaded HTML. Citations use a source section with `pdf_page: null`;
PDF provenance and page checks remain intact. Source URLs support attribution,
but reuse rights and health-professional validation are not implied.

Age-point articles are conservatively restricted to that completed month;
the 24-month material is still constrained by the API's second-birthday policy.
Other existing references serve intervening months. A short summary or passage
count does not establish comprehensive coverage or suitability for an individual child.

`evaluation/coverage-questions.json` contains 64 draft questions covering domains,
routines, statements, follow-ups, age overviews, safety, and unsupported requests.
It is **not** a labelled/scored test set and is not yet compatible with the scored
retrieval runner. Review relevant passage IDs and expected outcomes, then freeze
the development/held-out split before tuning. Immunisation cases remain pending.

Before enabling the expanded corpus:

1. Review summaries against their linked sections, reuse terms, age assignments,
   and safety context; arrange the human review tracked in #79.
2. Label the questions under #74, separating retrieval checks from answer-quality
   review under #78. Do not infer clinical correctness from a helpfulness score.
3. Evaluate a separate staging collection and compare with the original collection.
   Candidate uploads require an explicit `--allow-candidate-upload` and a
   `--collection` different from the configured application collection. The target
   must already exist; no collection is automatically created or cleared.
4. Compare retrieval and generation timing using the same questions, child ages,
   model, and routine. Include failures, cold requests, and repeated requests;
   report median and tail latency, not just the fastest answer.

### Response-time boundary

Research and preparation happen offline, not during a caregiver request. This
change retains the current model, one retrieval call, three-passage request limit,
and concise answer instructions. It does not add live web browsing, model-based
re-ranking, or a larger prompt. No speed improvement is claimed until live timing
is measured; provider load and quota can still affect response time. Do not remove
age, evidence, or safety checks to achieve a faster timing result.

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_reference_expansion.py tests/test_rag_data.py tests/test_retrieval.py
```

## Vaccination and common-concern review pack

`health-reference-expansion.json` contains 18 separate candidate summaries from
WHO, UNICEF, Kenya Ministry of Health, and NHS references. This material is not
enabled in the working app or included in the uploaded developmental expansion.
It covers vaccine education and side effects, a historical Kenya programme
update, temperature measurement, feeding during vomiting/diarrhoea, reflux,
nappy-area care, cough/cold concerns, and urgent warning signs. It is not a full
vaccination schedule, clinical triage service, or medication protocol.

```powershell
.\venv\Scripts\python.exe -m scripts.build_reference_expansion --pack data/health-reference-expansion.json --base data/processed/expanded/passages.jsonl --manifest data/processed/expanded/sources.json --output-dir data/processed/health-candidates
```

This preparation command is offline. Verify web sources directly at the URLs
and sections recorded in the reference pack; do not archive website HTML locally.
Original downloadable documents such as PDFs retain the existing file/page/hash
provenance workflow. Editorial summary fingerprints do not identify the original
web page or establish that its content has not changed. Website verification and
preparation happen outside caregiver requests; answers use indexed passages.

Every health candidate carries `clinical_review_required: true`, an explicit
country scope (`KE` or null for general education), and a release-blocked status.
Before enabling it, obtain qualified review and implement/test:

- Explicit country selection for vaccination schedules; do not borrow the crisis
  support location field or imply a historical announcement is a complete schedule.
- Warning-sign routing before retrieval or model generation, including numeric
  temperature reports, unusual vomit, reduced urine, breathing/colour changes,
  and serious reactions after vaccination. Existing regex checks are incomplete.
- Age-specific instructions, uncertainty handling, and professional referral when
  symptoms worsen, details are missing, or a caregiver remains concerned.
- No reassurance solely because a symptom followed vaccination or teething;
  no diagnosis, medication selection, doses, or unsourced treatment suggestions.
- A clear distinction between emergency referral, prompt professional advice,
  and general supportive education; UK service numbers must not be presented as
  Kenya or worldwide contacts.

The existing production routing is unchanged by preparing this pack. These review
flags are data metadata, not a claim that a clinical safety workflow is implemented.

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_health_reference_pack.py tests/test_reference_expansion.py tests/test_rag_data.py
```

## Reproduce on Windows

### Additional PDF evidence for common concerns

Two additional original documents are retained under `data/raw/pdfs/`:

| Source | Physical pages | Intended use |
| --- | ---: | --- |
| Public Health Agency, *Birth to Five 2025* | 174 | Selected caregiver-facing content on crying, stool changes, nappy care, teething, jaundice, and warning signs |
| Kenya Ministry of Health, *Clinical Guidelines for Level 1 Community Health Services (2024)* | 184 | Selected vaccine-purpose information and care-seeking guidance, not automatic clinical protocols |

`pdf-health-reference-expansion.json` records the original filenames, source URLs,
SHA-256 fingerprints, page counts, and 11 explicitly selected candidate summaries.
The builder verifies the original bytes and page count, confirms a section anchor
on each selected physical page, and records a normalized page-text fingerprint.
These checks establish traceability, not clinical correctness or a verbatim quote.

```powershell
.\venv\Scripts\python.exe -m scripts.download_reference_pdfs
.\venv\Scripts\python.exe -m scripts.build_reference_expansion --pack data/pdf-health-reference-expansion.json --base data/processed/health-candidates/passages.jsonl --manifest data/processed/health-candidates/sources.json --output-dir data/processed/pdf-health-candidates
.\venv\Scripts\python.exe -m scripts.index_rag --passages data/processed/pdf-health-candidates/passages.jsonl --manifest data/processed/pdf-health-candidates/sources.json --report data/processed/pdf-health-candidates/preparation-report.json
```

Run the earlier developmental and health pack preparation commands first. With
the current inputs the combined candidate corpus contains 182 passages: 106
original, 47 developmental web summaries, 18 health web summaries, and 11 PDF
health summaries. The uploaded developmental collection still has 153 points;
neither health pack is enabled in the working application.

Only original PDFs are downloaded. The downloader rejects non-PDF responses and
does not overwrite an existing document; pinned fingerprints in the selection
pack detect a changed source at build time. Publisher reuse rights still apply.
Do not bulk-index these books: they include older-child/adult material, regional
schedules and contact numbers, clinician-only medicine instructions, and guidance
that may need reconciliation with newer sources. The selected health summaries
remain release-blocked pending qualified review and symptom-routing evaluation.

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

## Activity precautions

`activity-safety-reference-expansion.json` contains five candidate prevention passages
from UNICEF and NHS covering play objects, falls, water activities and eating.
Original URLs and section labels are retained; no HTML copies are stored.
These are not emergency-treatment instructions or a complete activity-safety assessment.

The generation prompt requests a short relevant precaution only when supported by the
retrieved excerpts, within the existing 90-word answer limit. This adds no model call
or website request. It does not guarantee that every activity retrieves a precaution.
Review activity-and-precaution retrieval together before enabling the candidate pack.
The application collection is unchanged.

Build a separate local candidate after preparing the PDF health candidates:

```powershell
.\venv\Scripts\python.exe -m scripts.build_reference_expansion --pack data/activity-safety-reference-expansion.json --base data/processed/pdf-health-candidates/passages.jsonl --manifest data/processed/pdf-health-candidates/sources.json --output-dir data/processed/activity-safety-candidates
```

## Reading the library documentation

See [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
Start with `extract_text()` and `extraction_mode="layout"`, then read “Why Text Extraction
is hard.” The distinction explains why page text is preserved for review before selecting
passages: a PDF describes positioned drawing/text operations, not reliable paragraph or
table structure.
