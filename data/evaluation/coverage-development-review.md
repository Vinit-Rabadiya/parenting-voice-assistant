# Current baby-care coverage review - 30 October 2026

Active release: `caregiver_guidance_everyday_v4`, 216 passages, 45 manifest source
entries and 42 original URLs. Corpus SHA256:
`776133f6c59bb0e9506071b468f10ae1a14eaa1811bb8d95c73c464dd14a46f9`.
All remote payloads match the local release. All 184 v3 records are unchanged;
32 additions index the validated application care facts. V3 and the original
106-record baseline remain available for rollback. Clinical candidate packs
remain blocked.

## Substantive inventory

| Topic | Reviewed sources and scope | Boundary |
| --- | --- | --- |
| Feeding/nutrition | NHS first foods/preferences, UNICEF infant/toddler feeding and Kenya handbook. | Milk before six months; readiness-based solids; soft family foods and gentle preference support. No forced feeding or therapeutic formula/dose decisions. |
| Sleep | NHS routines and safer sleep, plus existing routine selections. | Back/flat infant sleep, clear separate cot, room sharing in the first six months. No raised cot, sleep guarantees or unsolicited timings. |
| Hygiene/clothing/oral care | NHS bathing, nappy care and tooth brushing; Reach Up dressing; SA bath-language activities. | Continuous water supervision, gentle skin care, no self-selected rash treatment; brushing begins after tooth eruption. |
| Soothing/bonding | Reach Up and UNICEF positive parenting through 24 months. | Respond to cues and ordinary needs; illness or inconsolable crying needs assessment. No shaking or violence. |
| Development/movement | WHO/UNICEF CCD, Reach Up, UNICEF age-labelled activities, HSE books and NHS conversation selections. | Opportunities to practise, not diagnostic milestone tests. Newborn turn-taking means gentle sounds and pauses without demanding a response. |
| Growth records/appointments | Kenya handbook and general NHS review preparation. | Bring local records, observations and questions. Do not copy overseas appointment schedules or diagnose from measurements. |
| Vaccination | Separately checked Kenya schedule and vaccine-education router. | Clinics confirm actual due doses, catch-up and regional eligibility. |
| Safety | UNICEF home precautions, NHS eating/toy safety and existing early danger routes. | Appropriate objects and supervision; urgent signs precede generation. Kenya contacts remain separately verified. |
| Outings | NHS shade/clothing precautions and existing travel-planning selection. | No blanket over the pram, overseas road rules or travel-medicine protocol. |
| Childcare/caregiver support | UNICEF separation/positive parenting and existing caregiver-support routes. | Gentle introductions and supportive routines; no diagnosis of anxiety or postpartum illness. |

## Age and domain coverage

The routine matrix counts stored tags at selected calendar-age checkpoints.
Age zero uses an eleven-day example; it is not a count of all birth-day content.

| Age (months) | Feeding | Bathing | Play | Reading | Dressing | Sleep | Soothing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 6 | 8 | 9 | 4 | 3 | 3 | 1 |
| 2 | 6 | 7 | 13 | 4 | 3 | 3 | 1 |
| 4 | 7 | 8 | 12 | 4 | 4 | 3 | 1 |
| 6 | 11 | 8 | 12 | 3 | 2 | 2 | 0 |
| 9 | 11 | 7 | 11 | 4 | 1 | 2 | 0 |
| 12 | 8 | 5 | 14 | 6 | 5 | 2 | 0 |
| 18 | 8 | 4 | 15 | 5 | 4 | 2 | 0 |
| 24 | 7 | 3 | 12 | 5 | 3 | 0 | 0 |

The general soothing facts apply through the second birthday, and toddler sleep
facts also apply at 24 months; they have no corresponding routine tag. Those
zero cells do not mean the named care facts are absent. Actual request selection
and replies were checked separately.

Domain totals after applying the hash-pinned baseline editorial annotations are
non-exclusive: cognitive 50, language 111, social/emotional 41, gross motor 21,
fine motor 38, responsive caregiving 37, nutrition 11, safety 16 and common
concerns 18. No new exact-text duplicates were introduced. Counts describe the
selected source collection, not comprehensive clinical coverage.

## Common-concern review

| Concern | Source selection and applicable boundary |
| --- | --- |
| Feeding difficulty/reflux | NHS reflux and food-preference selections: basic positioning, awake/sleep distinction, assessment after the first birthday. No individual feeding changes, raised cot or treatment duration. |
| Vomiting/diarrhoea | NHS stomach-upset guidance: usual feeds if tolerated, no weakened formula, hygiene and fluid-loss observations. Young infants need prompt advice; inability to retain fluids, green/bloody vomit and other danger reports use urgent handling. |
| Fever | NHS temperature checking and care: young-infant professional advice, observation and usual feeds; no medicine/dose selection or invented numeric thresholds. |
| Cough/cold | NHS cough/cold guidance: feeding/breathing observations, usual drinks and handwashing; professional advice about products. Breathing/swallowing difficulty requires urgent care. |
| Nappy irritation | NHS rash care: gentle cleaning/drying, avoiding irritants and assessment for persistence, spreading, discomfort or fever. Pharmacist advice for products. |
| Teething | NHS comfort/symptom pages: age-suitable rings, no freezing/neck cords. Young-baby symptoms do not prove teething; diarrhoea, fever or vomiting is not explained away as teeth. |
| Stool changes | NHS Best Start infant guidance: young-infant assessment, correct formula strength and no remedies from chat; suitable food variety only after starting solids. The overdue older constipation page remains excluded. |
| Newborn yellowing | NHS jaundice: prompt assessment, no sunlight treatment or severity estimate by colour. A reported symptom on a known day-zero profile bypasses generation. The selection is newborn-only. |
| Lost abilities/development concerns | CCD/Kenya concern guidance and general review preparation: record changes and seek assessment, without diagnosing or forcing a skill. |

## Traceability and overlap

All records resolve to an original source URL, title/publisher, page or section,
source/content fingerprints and age scope. The existing hash-pinned domain review
supplies non-exclusive annotations for the 106 baseline records without changing
them. All three original PDFs are present and match their manifest hashes; their
byte recheck is dated 30 October. Everyday web checks are dated 24 October and
basic-care checks 30 October. Known publisher review dates are retained; unknown
publication dates are not invented. NHS fussy-eater guidance has its next stated
review on 13 November 2026.

Fourteen contained-text pairs remain in the preserved baseline. Combined and
standalone selections have distinct identities/scopes/routine annotations;
containment alone does not justify deleting a labelled baseline record. The
caring-behaviour and birthday questions also received answer review. No query-
specific vector boosts, threshold changes or reranker were introduced.
Routine matrices count tags, not substantive coverage: generally applicable care
facts may have no UI-routine tag and still support the named topic at that age.

## Frozen retrieval results

The source-checked positive pools in `care-coverage-questions.jsonl` are pinned to
the release fingerprint and fixed dates. Five fresh questions were reserved after
development corrections and before final verification. Their results did not
guide further content, ranking or threshold changes. These are project-authored
pools, not exhaustive relevance labels or independent clinical gold standards.

| Group | Cases | Positive hit@4 | Mean positive-pool recall@4 | MRR | Mean retrieval ms | Observed age leaks |
| --- | --- | --- | --- | --- | --- | --- |
| Development | 20 | 19/20 | 0.8500 | 0.8042 | 395.3 | 0 |
| Earlier held-out | 12 including 3 unrelated | 9/9 | 0.9444 | 0.8704 | 332.4 | 0 |
| Fresh final held-out | 5 | 5/5 | 0.9000 | 0.8667 | 324.4 | 0 |

All three unrelated cases returned raw neighbours but were rejected by the
unchanged 0.50 gate. All locally known ineligible IDs were checked; these coverage
cases are not all age-boundary cases. The separate CI fixture explicitly checks
day zero, one week, six months and the second birthday with constant vectors,
which verify filtering rather than embedding quality.

The loss-of-ability development case remains a raw vector miss against its label
pool. The general concern wording selects the appropriate local assessment facts;
the delivered answer does not diagnose. That is not counted as a vector hit.
The combined `eval/results/care-coverage-answers-20261030.json` capture retains
initial findings, final retrieval and actual answers. Retrieval recall is not
answer accuracy. Answer/rubric review is in `coaching-quality-review.md`; final
signed-in acceptance is recorded once in `docs/progress-review.md` under #66.

---

# Initial development retrieval review

Corpus: 187 candidate passages in `caregiver_guidance_review_v1`.
Evidence: `eval/coverage-v1/development-results.json`, 36 development cases.
The held-out split has not been used for this review.

## Baseline

- Hit@4: 0.9412 across 34 positively labelled cases (32 hits, two misses).
- Mean recall against the initial labelled positive pool: 0.7108.
- MRR: 0.7574.
- Known age-ineligible passages returned: zero.
- Mean retrieval latency: 358.7 ms; generation and audio are excluded.

These are development results against first-pass editorial labels, not independent
or clinical validation. Preserve the baseline and labels rather than changing them
to make retrieval scores look better.

## Miss review

| Case | Observation | Next action |
| --- | --- | --- |
| cv21: caring behaviour | Returned time-to-play, conversation, caregiver stress and toy-availability passages instead of the labelled caring-gestures passage. The highest score was 0.6124, so a 0.50 threshold alone cannot establish semantic relevance. | Inspect where the caring-gestures passage ranks and assess a general retrieval improvement on the development set; do not add a question-specific rule. |
| cv35: changing clothes | Returned grasping, everyday-care conversation, a combined face-play/chat passage and fall precautions. The combined passage includes talking during changing and may be relevant despite not being in the positive pool. The highest returned score was 0.4658. | Record a possible incomplete label pool; review routine tags and combined/standalone passage duplication before changing ranking. Keep original labels and baseline intact. |

## Reporting corrections

The original console `PASS` meant only that no forbidden age ID was returned.
It did not mean the correct references were retrieved. The evaluator now reports
`AGE_OK` separately from `HIT`/`MISS` and adds the existing evidence-gate outcome.

The no-evidence examples cv51 (first foods before six completed months) and cv54
(car repair) both returned raw candidates. Vector search returning neighbours is
not itself an answer-generation failure. The original report did not record the
gate outcome, and `0/0` missing-topic results were not rejection evidence.
Re-run development evaluation into a new output file to record the actual gate
decision using the current threshold. This does not call the generation model.

Broad first/second-birthday cases cv44 and cv47 each retrieved one of four labelled
domain passages. Investigate cross-domain coverage before claiming balanced age
overviews. Do not merely increase the live prompt size or weaken age filtering.

## Read-only ranking diagnosis

Two additional queries inspected up to 100 age-filtered candidates in the same
review collection, using only development cases. No collection or label changes
were made, and no held-out results were examined.

- **cv21:** the labelled caring-gestures passage ranks eighth with score 0.5117.
  It is within the normal candidate pool of 20, but outside the final four.
  Fetching more candidates alone will not correct this final ordering. The
  higher-ranked results concern caregiver availability and stress rather than
  the child's caring behaviour.
- **cv35:** `7726540107e02bed6b14` (Chat with baby) ranks ninth at 0.4235,
  but has routine tags `feeding`, `bathing`, `changing`. The request routine is
  `dressing`, so the current exact-match routine filter excludes it. The other
  labelled dressing activity `c5820d9bfa874c8662a6` ranks nineteenth at 0.3489.
  Both labelled scores are below the existing 0.50 evidence threshold; fixing
  the routine-name mismatch alone will not establish an answerable result.
- The returned combined passage `f78a77c6f0225e3e5692` includes chat during
  changing, but is untagged and absent from this case's initial positive pool.
  Preserve this as a label-pool limitation rather than silently revising the
  baseline to improve the reported score.

### Implementation order

1. Define and test canonical routine aliases consistently during preparation and
   retrieval. Review whether `changing` means clothes/dressing or nappy care in
   each source; do not blindly rewrite every occurrence into `dressing`.
2. Compare a general ranking/indexing improvement on the development set in a
   separate collection. Do not hard-code boosts for these question IDs or lower
   the evidence threshold to make the two examples pass.
3. Recheck development relevance, no-evidence rejection, age isolation and
   latency before enabling any retrieval change in the application.

## Index comparison decision

All three development runs use the same 36 questions, source text, initial labels,
age eligibility, top-four limit and 0.50 threshold. No held-out results were used.

| Variant | Hit@4 | Recall@4 | MRR | Mean retrieval latency |
| --- | --- | --- | --- | --- |
| Original text and tags | 0.9412 | 0.7108 | 0.7574 | 359.0 ms |
| Original text, reviewed routine correction | 0.9706 | 0.7255 | 0.7647 | 355.5 ms |
| Context-enriched vectors, reviewed routine correction | 0.8235 | 0.7279 | 0.6838 | 354.4 ms |
| Local TinyBERT reranker, reviewed routine correction | 0.9412 | 0.6667 | 0.7255 | 449.7 ms |

Each variant returned zero known age-ineligible IDs and rejected both labelled
no-evidence examples. These are two rejection examples, not comprehensive safety
validation. Small timing differences across single runs do not establish a speed gain.

**Decision:** retain the reviewed routine correction as the preferred candidate.
Do not promote context-enriched embeddings: compared with the routine-only variant,
they introduce misses on cv01, cv03, cv14, cv32 and cv47. The small recall increase
does not outweigh the drop in hit rate and reciprocal rank. The experimental option
remains explicit and staging-only for reproducibility, not part of the default path.

### Remaining findings

The local CPU TinyBERT reranker is also not selected for activation. Its measured
mean reranking portion was 37.7 ms, with initialization recorded separately.
It retained the caring-behaviour miss and introduced a feeding-hygiene miss
(cv39), while reducing labelled recall and MRR compared with routine-only.
The total latency difference is not attributable entirely to reranking: network
and first-query overhead also vary across these single development runs.

- **Changing clothes:** cv35 now retrieves the labelled Chat with baby passage,
  but the evidence gate accepts none of the returned passages. The correction
  fixes a retrieval exclusion, not end-to-end answer availability. Do not claim
  that this input now receives an answer or lower the threshold just for this case.
- **Caring behaviour:** cv21 remains a miss and its returned caregiver-support
  passages pass the score threshold. Similarity is not proof that they answer
  the requested child-behaviour topic. Semantic ranking still needs improvement.
- **First birthday:** cv44 returns communication, everyday interaction and a
  first-birthday movement passage; only the last is in the initial positive pool.
  A labelled recall of 0.25 alone does not establish that the answer lacks all
  other developmental domains. Review actual source support and generated output.
- **Second birthday:** cv47 returns general play guidance, turn-taking,
  construction play and caregiver-child conversation. Several useful passages
  are outside the initial four positive labels. Preserve this label-pool limitation.

The canonical page-37 selection now includes the reviewed dressing tag for future
builds. Existing corpus files, labels and evaluation splits are not regenerated:
doing so would invalidate the pinned baseline fingerprint. The application collection
remains unchanged. A final label pool needs independent review; do not rewrite this
one after seeing results and then report the revised scores as an unbiased improvement.

## Recorded-score threshold comparison: 24 October 2026

### Frozen retrieval test result

`eval/coverage-v1/held-out-routines-results.json` records the first held-out run
against the pinned 187-passage routine corpus. There are 16 cases: 15 answerable
and one unsupported. Hit@4 is 1.0, labelled-pool Recall@4 is 0.8222 and MRR is
0.7278, with zero observed age leaks. Mean retrieval time is 372.9 ms.
The unsupported guarantee request passes the raw similarity gate: it is not
counted as a successful rejection. Retrieval alone does not establish that an
answer would make that guarantee. These findings have not been used to change
the cutoff or ranking. They do not validate the separate 184-passage release.

### Source-checked everyday release inventory

The 184-passage, 25-source derived corpus preserves the original 106 records
and adds 78 source-checked selections. Thirty-three additions have an explicit,
ID-scoped correction of a mixed pack's blanket clinical flag: language, play,
participation and everyday planning, not vaccine or symptom education.
The 273-record candidate input remains unchanged and clinical candidates stay
excluded. Editorial checking is not professional validation of the older baseline.

Corpus SHA256: `9122e08e6f827859f25ea80cbd3b6b257cd63bdd9b31e7fb30ac22ebefc2940c`.
Collection: `caregiver_guidance_everyday_v2`, prepared separately from the
application collection. It is not yet activated in the application.

| Completed months | Feeding | Bathing | Play | Reading | Dressing | Sleep | Soothing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 (11 days) | 5 | 8 | 9 | 4 | 3 | 3 | 1 |
| 2 | 5 | 7 | 13 | 4 | 3 | 3 | 1 |
| 4 | 6 | 8 | 12 | 4 | 4 | 3 | 1 |
| 6 | 9 | 8 | 12 | 3 | 2 | 2 | 0 |
| 9 | 9 | 7 | 11 | 4 | 1 | 2 | 0 |
| 12 | 6 | 5 | 14 | 6 | 5 | 2 | 0 |
| 18 | 6 | 4 | 15 | 5 | 4 | 2 | 0 |
| 24 | 5 | 3 | 12 | 5 | 3 | 0 | 0 |

Counts represent age-eligible tags, not topic completeness or answer quality.
Non-exclusive editorial domains: cognitive 50, language 111, gross motor 21,
fine motor 38, social-emotional 41 and responsive caregiving 29. Sleep at exactly
24 months and soothing after six months remain explicit coverage gaps in this
release. Fourteen same-source containment pairs remain unchanged because combined
and standalone selections can have different age eligibility; no automatic
deletion or claim of complete duplicate resolution is made.

Input: `eval/coverage-v1/development-routines-results.json`, the existing 36-case
development run against the routine-corrected 187-passage collection. The original
report, labels, split and rankings are unchanged. These are not new network
measurements or results for the 273-passage candidate corpus.

| Cutoff | Answerable: labelled evidence accepted | Answerable: no evidence accepted | Answerable: only unlabelled evidence accepted | Unsupported: accepted | Unsupported: rejected |
| --- | --- | --- | --- | --- | --- |
| 0.40 | 33 | 0 | 1 | 1 | 1 |
| 0.45 | 32 | 0 | 2 | 1 | 1 |
| 0.50 | 29 | 2 | 3 | 0 | 2 |
| 0.55 | 23 | 8 | 3 | 0 | 2 |
| 0.60 | 17 | 12 | 5 | 0 | 2 |

At 0.50, cv12 and cv35 receive no evidence. Cases cv14, cv21 and cv32 accept
passages outside their positive label pool. This last category is a review flag,
not proof that every accepted passage is irrelevant: the editorial label pool
is incomplete. It also prevents counting a high-scoring non-answer as success.

Lower cutoffs recover some labelled evidence but admit one unsupported example;
higher cutoffs reject more answerable requests. The two unsupported examples
are too few to establish a reliable false-acceptance rate. Recorded scores are
rounded and cannot replace evaluation of a pinned current corpus.

Decision: retain the application's provisional 0.50 cutoff. This comparison is
development evidence, not final calibration or held-out validation. The tool
rejects held-out or unidentified splits for cutoff comparison. Independent labels,
current-corpus evaluation and final outcome review are required for a release claim.

### Implementation verification

Commits `e01978c`, `18fd6ac` and `2e9e484` contain the retrieval safeguards,
audit tools/domain annotations and regression tests respectively. Full configured
checks passed: 803 Python tests, 151 frontend tests, 7 audio tests, both linters
and the frontend production build.

Two read-only feeding-reference probes at six months, using exact age 183 days,
returned three passages and three above-cutoff evidence passages in each mode:
3.016 seconds for application retrieval and 1.711 seconds for explicit candidate
evaluation in `caregiver_guidance_activity_review_v5`. These are individual
network observations, not repeated latency benchmarks, generated-answer timings
or signed-in browser validation. No generation request or collection write was made.
