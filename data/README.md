# RAG data preparation

The selected reference corpus supports retrieval, not model training. The current prepared
corpus contains 106 editorially selected passages: 18 WHO/UNICEF counselling-card passages,
75 Reach Up passages, and 13 Kenya handbook passages. Selection and extraction checks do
not constitute expert validation of developmental appropriateness.

## Expanded reference candidates

The broader target inventory is `data/baby-care-coverage-plan.json`. It lists
everyday baby-care topics, responsible issues and the review requirements before
a topic can be described as supported. Its status is planned, not activated.
Prioritise gaps against that inventory rather than increasing passage counts
without a coverage purpose. Preserve the distinction between source preparation,
editorial relevance review, qualified health review and live activation.

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

## Broad baby-care source collection

See [baby-care-source-catalogue.md](baby-care-source-catalogue.md) for the 64-entry
collection of books/manuals, official articles, guidelines and research papers.
It distinguishes existing references, newly downloaded PDFs, checked publication
pages and abstract-only research records. Collection does not activate sources or
replace earlier frozen corpus revisions. Website HTML is not retained.

The 2026 Birth to Five handbook and the open-access Jeong parenting paper are
retained under `data/raw/pdfs/`; their page counts and hashes are in the catalogue.
The 2025 handbook remains available for reproducibility. Full-document selection,
Kenya applicability, health review and reuse permissions remain separate tasks.

## Activity precautions

### Practical-care passage revision

`practical-care-reference-expansion.json` now selects 77 passages from 25 sources,
including explanations, practical actions, precautions and care-seeking boundaries.
It covers feeding difficulties, reflux, vomiting, food refusal, first foods,
nappy irritation, teething, fever, newborn jaundice, toddler stool concerns,
growth records, health visits, caregiver transitions, outings, postpartum support
and general vaccine safety. Original source headings are retained alongside each
passage's title. Source dates are retained where checked; missing dates are not
invented.

Six existing sources are revised explicitly: reflux, diarrhoea/vomiting, nappy
rash, WHO vaccine safety, UNICEF toddler feeding and UNICEF two-year development.
The separate build removes 15 old passages and adds 77 selections:
**211 - 15 + 77 = 273 passages from 55 sources**. This avoids
retaining two source revisions in the same candidate corpus. Original inputs and
the 187/211-passage evaluation revisions are unchanged.

`source_heading` identifies the relevant original heading, `guidance_kind`
distinguishes explanation/action/precaution/referral, and optional
`applicability_conditions` records restrictions for review. These fields are not
an implemented clinical decision engine; age eligibility alone does not prove
that advice applies to a particular child. Important conditions also remain in
the passage text. All new selections remain blocked pending health review.

```powershell
.\venv\Scripts\python.exe -m scripts.build_reference_expansion --pack data/practical-care-reference-expansion.json --base data/processed/everyday-care-candidates/passages.jsonl --manifest data/processed/everyday-care-candidates/sources.json --replace-existing-sources --output-dir data/processed/practical-care-activity-candidates
.\venv\Scripts\python.exe -m scripts.index_rag --passages data/processed/practical-care-activity-candidates/passages.jsonl --manifest data/processed/practical-care-activity-candidates/sources.json --report data/processed/practical-care-activity-candidates/preparation-report.json
```

Source replacement requires explicit opt-in, known source IDs, unchanged source
URLs and a different output directory. The report records the input fingerprint
and removed count. Neither command uploads content unless indexing is separately
invoked with its upload options. The 211-passage labels do not apply to this new
corpus fingerprint; review a new evaluation revision before measuring retrieval.

The pack's `selection_review` records exclusions and limits. It does not include
whole-book extraction, a complete Kenya vaccine schedule, medical treatments or
a complete formula/water preparation protocol. The 2026 handbook and research
papers remain collected references, not automatically indexed advice.

The earlier 248-passage revision (45 selections replacing eight passages) is
uploaded only to `caregiver_guidance_practical_review_v1`. Its frozen local files
remain in `data/processed/practical-care-candidates`. The revised local build
removes incomplete food-covering/reoffering advice without inventing storage rules.
Its byte SHA-256 is `d236ec2e18d6651bae32711f7642f9365b81343f971167a72999bb43b821838c`.
It was uploaded to separate text-only and context-embedding v2 review collections,
not activated. The 265-passage v3 build adds 17 everyday communication selections
from four NHS age-band pages and one UNICEF activities page. Its byte SHA-256 is
`5d3ff3a6a37801d617b176ebe979c1d7cb494666b9752dc549b2a6cd7f0bb520`;
it is uploaded only to `caregiver_guidance_communication_review_v3`. The later
273-passage revision separates activities into more focused passages and adds
HSE book sharing and South Australia education bath-language selections. It is
uploaded only to `caregiver_guidance_focused_review_v4`, with file-byte SHA-256
`c6d85a802399717e4f48c054d59fee6706fbef79179c27824e5ff79c9cf9e7cd`.
The latest activity-wording revision retains 273 passages/55 sources, with focused
pretend-play and interactive-reading descriptions. It is uploaded only to
`caregiver_guidance_activity_review_v5` and its file-byte SHA-256 is
`687112416aa0e9c2797508a1aa6ad6b1db5aeca58047dfb7acafe2550be898b3`. The application
collection remains unchanged. Do not reuse v1 labels/fingerprints for these revisions.
`practical-care-cases.json` contains 24
artificial examples with first-pass labels in one file: 18 retrieval cases and six
workflow cases. Exported files are retained under `eval/practical-care-v1/`.
Development retrieval results and both three-answer captures are under
`eval/results/`. See `data/evaluation/coaching-quality-review.md` for findings;
these are not clinical approval or final held-out results.

The coaching capture command can reuse selected development queries from that
export without copying a separate question set:

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_coaching --retrieval-cases eval/practical-care-v1/questions.jsonl --cases pc01 pc06 pc16 --collection caregiver_guidance_practical_review_v1
```

This previews without network calls. Live capture additionally requires `--live`,
a new `--run-id` and the exact `--corpus-revision sha256:...` from the export.
Only development IDs are accepted through this option. The capture evaluates
three-passage service responses, not signed-in storage, ASR or TTS. Add
`--follow-up "What else can I try?"` to capture a synthetic contextual follow-up;
at most three follow-up options are accepted. This does not test authenticated
history persistence. Raw prompts and evidence are retained for reproducibility; only
artificial questions belong in these version-controlled examples.

Add `--retrieval-only` to record routing, raw matches and gated evidence without
calling Gemini. `evidence_available` means only that a passage passed the gate;
it is not a generated answer or a relevance/clinical accuracy score. This mode
cannot be combined with follow-up capture, because it produces no answer context.

`--keyword-search` is an evaluation-only comparison that removes common request
words from retrieval text while preserving the original generation message.
The 40-case comparison lost existing matches and was not adopted in application
retrieval. It is not a semantic relevance test or a recommended production setting.

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_practical_care_pack.py tests/test_reference_expansion.py tests/test_health_reference_pack.py tests/test_everyday_care_pack.py
```

These tests check preparation contracts, preserved metadata, source replacement
and selected age boundaries. They do not score actual generated answers or give
clinical approval.

### Everyday-care expansion

`everyday-care-reference-expansion.json` adds 24 candidate passages from seven
UNICEF and NHS web pages covering breastfeeding support, formula safety principles,
toddler sleep, nappy routines, oral care and crying/soothing. Source URLs, section
labels, stated review dates and Kenya-applicability notes are retained. Website
HTML is not stored. These are focused summaries, not complete clinical protocols.

`data/evaluation/everyday-care-gap-audit.json` records the pre-expansion gaps,
selected additions and remaining limitations. Exact duplicate IDs/text are checked
by the builder; semantic overlap still requires editorial review. Formula mixing
instructions, diagnostic thresholds, medicine advice and UK service numbers are
not selected. First-teeth advice is conditional on teeth being present.

The NHS formula-preparation and toddler-sleep pages are past their stated
review-due dates as checked on 22 October 2026. `source_freshness` records this;
the build report lists affected sources. A current-source check and qualified
Kenya-applicability review are required before activation. A date within the stated
review window is not proof of clinical approval.

```powershell
.\venv\Scripts\python.exe -m scripts.build_reference_expansion --pack data/everyday-care-reference-expansion.json --base data/processed/activity-safety-candidates/passages.jsonl --manifest data/processed/activity-safety-candidates/sources.json --output-dir data/processed/everyday-care-candidates
.\venv\Scripts\python.exe -m scripts.index_rag --passages data/processed/everyday-care-candidates/passages.jsonl --manifest data/processed/everyday-care-candidates/sources.json --report data/processed/everyday-care-candidates/preparation-report.json
```

The combined local corpus has 211 passages from 36 sources. It is not uploaded or
enabled. The frozen 187-passage evaluation remains unchanged; broader retrieval
and answer-quality validation require a separately reviewed revision. Topic depth,
helpful follow-ups and health boundaries remain open under #76, #103 and #102.

### Expanded-reference evaluation

`everyday-care-questions.json` and `everyday-care-labels.json` define a separate
18-case revision: 13 retrieval cases and five workflow cases. The positive labels
identify direct text support in candidate passages, not clinical approval or an
exhaustive relevance judgement. The corpus fingerprint is checked before export.
`eval/everyday-care-v1/` preserves the exported split; `eval/coverage-v1/` is unchanged.
No live results or answer-quality scores have been recorded for this revision.

To reproduce the export, choose a new output directory; existing exports are not
overwritten:

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_retrieval_cases --corpus-dir data/processed/everyday-care-candidates --inventory data/evaluation/everyday-care-questions.json --labels data/evaluation/everyday-care-labels.json --output-dir eval/everyday-care-v2
```

After uploading the exact pinned candidate corpus to a separate staging collection,
evaluate development retrieval without changing application configuration:

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_retrieval --queries eval/everyday-care-v1/questions.jsonl --corpus data/processed/everyday-care-candidates/passages.jsonl --collection caregiver_guidance_everyday_review_v1 --split development --output eval/results/everyday-care-development.json
```

The collection named above has not been uploaded by this work. Do not run the
evaluation against a missing or differently populated collection. Preserve held-out
cases for final evaluation. `scripts.evaluate_coaching --collection` can target a
staging collection for the existing coaching-quality questions; it does not measure
authentication, persistence, speech recognition, playback or multi-turn UI behaviour.

### Response outcomes and caregiver ratings

`backend/services/care_response.py` provides conservative fixed next steps when
the evidence gate returns no passages: clarification, insufficient baby-care
references, professional referral or an explicitly unrelated topic. This is a
limited English wording heuristic, not a complete intent classifier or medical
assessment. Unknown wording is clarified rather than automatically rejected.
Recognised danger signs and vaccination notices retain priority in the endpoint.
The existing `no_evidence` status is retained; `response_kind` distinguishes the
wording in current responses and saved history. These messages carry no generated
advice or supporting citations. The similarity threshold is unchanged and there
is no extra generation call. Statements are accepted as requests for support.

Feedback accepts either historical Helpful/Not helpful values or a numeric scale:
1 Not helpful, 2 Slightly helpful, 3 Somewhat helpful, 4 Helpful, 5 Very helpful.
Optional reasons are unclear, repeated advice, did not answer the message and not
suited to the child's age. The existing account-scoped feedback endpoint and
message storage are reused. Updates replace feedback without creating an
administrator review state for private messages. Historical booleans are not converted into numbers; aggregate those two
scales separately. Ratings describe perceived helpfulness, not clinical accuracy.
The aggregate-only administrator overview is documented in the root README.
It does not expose individual questions, answers, comments or source records.
Private feedback is not exported for evaluation or used for automatic training.

Local source/preparation checks passed before these application changes. For a
targeted check of the response, feedback and evaluation changes, run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_care_response.py tests/test_feedback_ratings.py tests/test_evidence_gate.py tests/test_conversations.py tests/test_conversation_context.py tests/test_coaching_evaluation.py tests/test_coaching_service.py tests/test_retrieval_cases.py tests/test_everyday_care_pack.py tests/test_reference_expansion.py tests/test_health_reference_pack.py
npm.cmd --prefix frontend run test:ui
```

Alternatively, `npm.cmd run check` runs the full configured suite, lint and build;
there is no need to run both the targeted commands and the full suite.

Signed-in checks: send a baby-care statement, send an unrelated request, ask an
unclear follow-up in a new conversation, and confirm recognised danger reports
still bypass generation. Save a numeric rating with a reason, reopen the chat,
edit it and check that the saved selection returns. Verify both feedback scales
and account isolation. Do not use the candidate-content counts as evidence that
all baby-care topics or clinical concerns are covered.

### Vaccination routing boundaries

Vaccination handling is Kenya-only. The backend defaults `vaccination_country`
to `KE`; there is no country selector and clients do not need to send the field.
Explicit non-Kenya or null values are rejected rather than silently reassigned.
This scope is not inferred from the separate crisis-support location.
Kenya context is retained with vaccination notices in conversation history and
legacy interactions. Existing history metadata is preserved rather than rewritten.

`backend/services/vaccination.py` currently routes recognised English vaccine
questions to a fixed `vaccination_notice`: individual clinical assessment or
Kenya references awaiting review. These notices
do not call Qdrant or Gemini and do not supply vaccine schedules, catch-up doses
or individual reaction assessments. Existing recognised danger/crisis routing
runs first. The notice is stored through the same response path as other chat
messages; normal coaching is unchanged. Keyword routing is not comprehensive
medical triage, and Kenya-only scope does not approve or enable health content.

`data/evaluation/vaccination-source-review.json` records the current source
reconciliation gap. The older guideline and later programme announcements do
not establish a complete current schedule. The proposed refresh policy is not
yet an implemented approval system. Qualified review and educational-generation
integration remain outstanding under #100; common concerns remain under #102.

### Optional local reranking comparison

`scripts/rerank_retrieval.py` wraps the existing retriever for evaluation only.
It uses `cross-encoder/ms-marco-TinyBERT-L2-v2` on CPU to score question/passage
pairs, with one model instance loaded per evaluation process. The first model
load can download weights and take longer; initialization time is recorded
separately. This experiment adds local compute and optional dependencies, not
another Gemini request. It is not enabled in the application.

For a top-four comparison, both baseline and reranked runs query the same raw
20-candidate budget with existing age/routine filtering. The reranker changes
ordering only. Original cosine scores remain unchanged for the evidence gate;
cross-encoder scores are neither confidence probabilities nor substitutes for
the current threshold. Record relevance, gate outcomes, initialization and warm
reranking latency before deciding whether to adopt it.

```powershell
.\venv\Scripts\python.exe -m venv eval/.venv
.\eval\.venv\Scripts\python.exe -m pip install -r requirements-evaluation.txt
.\eval\.venv\Scripts\python.exe -m pip check
.\eval\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --queries eval/coverage-v1/questions.jsonl --split development --collection caregiver_guidance_routines_v1 --corpus data/processed/activity-safety-candidates/passages.jsonl --output eval/coverage-v1/development-rerank-results.json --rerank
```

Use a clean environment without `--system-site-packages`; this prevents optional
ML dependency updates from changing the application environment. Direct model-runtime
versions are recorded in `requirements-evaluation.txt`; this is not a complete
transitive lockfile. Check dependency consistency before running the model.

The optional evaluation dependencies include a local ML runtime and may require
substantial downloads. They are separate from application requirements. No model
is installed or downloaded by ordinary unit tests; tests inject a fake scorer.
Held-out execution is explicitly refused for this experimental option.

### Development index comparison

Keep the source corpus and editorial label fingerprint fixed during this comparison.
Index-time variants preserve source text, citation metadata, passage IDs and age
eligibility. `data/routine-corrections.json` adds `dressing` to the individually
reviewed Chat with baby passage without globally rewriting `changing`.

| Collection | Search input | Routine metadata |
| --- | --- | --- |
| `caregiver_guidance_review_v1` | Original passage text | Original tags |
| `caregiver_guidance_routines_v1` | Original passage text | Reviewed correction |
| `caregiver_guidance_context_v1` | Title, domain, routine labels, original text | Reviewed correction |

The optional `--embedding-context` and `--routine-corrections` indexing flags
cannot upload into the configured application collection. They do not overwrite
the original preparation report. Context fields affect search vectors only;
the answer model still receives original source text. They are experiments,
not demonstrated improvements until development results are compared.

The completed development comparison favours the routine-only correction
(Hit@4 0.9706, MRR 0.7647). Context-enriched vectors reduced Hit@4 to 0.8235
and are not selected for activation. See
`data/evaluation/coverage-development-review.md` for results and remaining gaps.
The dressing metadata correction is also retained in the canonical page-37
selection for future builds. Do not rebuild pinned evaluation corpora in place.
The changing-clothes case still has no accepted evidence at the current threshold;
an improved retrieval hit is not proof of a successful generated answer.

After the two variant collections have been prepared, run:

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_retrieval --queries eval/coverage-v1/questions.jsonl --split development --collection caregiver_guidance_routines_v1 --corpus data/processed/activity-safety-candidates/passages.jsonl --output eval/coverage-v1/development-routines-results.json
.\venv\Scripts\python.exe -m scripts.evaluate_retrieval --queries eval/coverage-v1/questions.jsonl --split development --collection caregiver_guidance_context_v1 --corpus data/processed/activity-safety-candidates/passages.jsonl --output eval/coverage-v1/development-context-results.json
```

Compare the same questions, positive labels, threshold and top-four limit across
all three collections. Check regressions as well as improvements, including
no-evidence rejection and latency. Do not tune on the held-out split.

### Coverage review

Run `python -m scripts.prepare_coverage_review` after building the complete candidate
corpus. It writes `eval/review/caregiver-coverage/coverage.md` and
`question-review.json`. Existing output is never overwritten; use `--output-dir`
for a new review revision. The report identifies missing routine/age combinations.
The review sheet records age-eligible IDs, not relevance labels or retrieval results.
Expected passages and outcomes must be reviewed before splitting or scoring.

The 187-passage candidate audit identifies no sleep-tagged references eligible at
exactly 24 months. The original 106 passages have no developmental-domain metadata;
their domains need editorial classification rather than inference from routine tags.
Parent/colleague wording, independent relevance review and live retrieval
evaluation remain outstanding under #74. Qualified health review and current Kenya
schedule reconciliation remain outstanding under #100; no clinical approval is implied.

### Activity v5 coverage checkpoint — 24 October 2026

The latest candidate contains 273 passages from 55 sources. Its file-byte SHA-256
is `687112416aa0e9c2797508a1aa6ad6b1db5aeca58047dfb7acafe2550be898b3`.
The matrix below uses `coverage_markdown` from `scripts/prepare_coverage_review.py`
with evaluation date 2026-10-24. Profile dates use the shared calendar-age helpers;
the newborn example is 11 days old and the final row is the exact second birthday.
The earlier 187-passage report is retained as historical evidence, not overwritten.

| Age (months) | Feeding | Bathing | Play | Reading | Dressing | Sleep | Soothing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 23 | 8 | 10 | 4 | 4 | 4 | 13 |
| 2 | 23 | 7 | 14 | 4 | 4 | 4 | 13 |
| 4 | 24 | 8 | 13 | 4 | 5 | 4 | 13 |
| 6 | 31 | 8 | 13 | 3 | 3 | 3 | 12 |
| 9 | 31 | 7 | 12 | 4 | 2 | 3 | 12 |
| 12 | 26 | 5 | 15 | 6 | 6 | 5 | 5 |
| 18 | 26 | 4 | 16 | 5 | 5 | 5 | 5 |
| 24 | 22 | 3 | 13 | 5 | 4 | 3 | 5 |

Counts show eligible tagged passages, not distinct activities, relevant retrieval
results or approved guidance. A passage can contribute to several columns. The
previous zero sleep cell at the second birthday is now three candidate passages;
this resolves the missing-tag count, not clinical review or live activation.
The original 106 passages still need explicit developmental-domain classification.
Remaining tagged records include language (29), common concerns (39), responsive
caregiving (24), safety (23), social-emotional (12), nutrition (11), immunisation
(11), cognitive (10), gross motor (5) and fine motor (3). Topic labels such as
nutrition and common concerns are not developmental domains.

Reproduce the matrix without writing another review sheet:

```powershell
.\venv\Scripts\python.exe -c "from datetime import date; from pathlib import Path; from scripts.index_rag import load_passages, validate_source_references; from scripts.prepare_coverage_review import coverage_markdown; p=Path('data/processed/practical-care-activity-candidates/passages.jsonl'); rows=load_passages(p); validate_source_references(rows,p.with_name('sources.json')); print(coverage_markdown(rows,date(2026,10,24)))"
```

First-pass passage labels are now recorded in `data/evaluation/coverage-labels.json`.
They include reasons based on passage text and are not an exhaustive gold standard.
Run `python -m scripts.prepare_retrieval_cases` to validate them against the pinned
corpus and create `eval/coverage-v1/questions.jsonl`, a separate workflow-case file,
and a fingerprint manifest. The export contains 52 retrieval cases and 12 workflow
cases (conversation context, scope, referral or blocked health education).
The reproducible 70/30 split is assigned across all 64 cases before retrieval.
Existing output cannot be overwritten. This first-pass baseline still needs
independent relevance review and real parent/colleague wording for final claims.

After the labelled 187-passage candidate corpus is uploaded to a separate staging
collection, evaluate only the development split first:

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_retrieval --queries eval/coverage-v1/questions.jsonl --split development --collection caregiver_guidance_review_v1 --corpus data/processed/activity-safety-candidates/passages.jsonl --output eval/coverage-v1/development-results.json
```

This command requires that exact candidate collection to exist; the older
153-passage collection is not the labelled corpus. It measures Recall@4 against
the labelled positive pool, MRR and known age-ineligible IDs, not generated-answer
quality. Do not run or inspect held-out results during tuning. Keep the original
12-case evaluation unchanged for historical comparisons.

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

## Reference validation checkpoint: 24 October 2026

The current candidate audit is [coverage.md](../eval/review/caregiver-coverage/coverage.md):
273 passages from 55 sources, including 122 passages blocked for health review.
The original 106 passages now have content-based, non-exclusive domain annotations
in `data/passage-domain-review.json`. The annotation file pins the original corpus
hash and includes an anchor from each selected passage. It does not modify source
text, frozen evaluation labels or the application collection.

Fourteen same-source containment pairs identify combined activities and their
standalone communication selections. They are retained: removing one without
reviewing age eligibility and the surrounding activity would discard information
or invalidate earlier evaluation. The report also identifies missing source check
dates and computes overdue publisher review dates at the chosen audit date.

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_coverage_review --corpus-dir data/processed/practical-care-activity-candidates --domain-review data/passage-domain-review.json --evaluation-date 2026-10-24 --audit-only
.\venv\Scripts\python.exe -m scripts.inspect_relevance_scores --results eval/coverage-v1/development-routines-results.json --compare 0.40 0.45 0.50 0.55 0.60
```

The first command prints an audit without creating question labels or overwriting
an existing review. The second compares recorded development scores; it neither
selects a threshold nor reads held-out results. Its interpretation and measured
trade-offs are in `data/evaluation/coverage-development-review.md`.

### Separation of review content from normal chat

`RetrievalService` excludes candidate records, records blocked for health review,
and records requiring clinical review from normal requests. The existing live
corpus continues through the existing retrieval and evidence-gate path.
Changing a collection setting alone does not approve review-only records.

Evaluation of unapproved material requires both a separate `--collection` and
`--allow-candidate-content` in `scripts.evaluate_retrieval` or
`scripts.evaluate_coaching`. Add that flag to the separate-collection evaluation
commands above when reproducing candidate experiments. It cannot be used with
the configured application collection. Evaluation manifests record the flag;
age and routine filters still apply. Review mode is not a frontend option,
clinical approval mechanism or permission to publish candidate answers.

### Source currency

The NHS formula-preparation and young-child sleep pages were checked on
24 October 2026 and still show review-due dates of 31 August 2026 and
31 March 2026 respectively. They remain flagged; availability is not approval.
Original URLs and applicability restrictions are retained with the candidates.

The [Kenya Ministry of Health programme announcement](https://www.health.go.ke/node/1955)
identifies routine typhoid vaccination at nine months. That specific update does
not establish a complete current national schedule. The source-review record is
`data/evaluation/vaccination-source-review.json`. Vaccine education remains
disabled until current schedule reconciliation and qualified review are recorded.
