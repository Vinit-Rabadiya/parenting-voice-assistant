# Coaching quality review

## Method

Initial development review of actual retrieved evidence and generated answers, not an
accuracy benchmark or expert ECD validation. Questions are fixed before this review run.
Use synthetic profiles only; do not include caregiver or child personal information.

Evaluation date: 20 October 2026. Six-month profile: birth date 20 April 2026.

| ID | Question | Routine | Expected behaviour |
| --- | --- | --- | --- |
| cq01 | How can I help my baby learn during play? | play | Practical play actions supported by age-eligible references. |
| cq02 | How can I talk to my baby while feeding? | feeding | Communication guidance related to feeding; acknowledge any evidence gap. |
| cq03 | How do I repair a car engine? | none | Decline unrelated advice; no invented automotive answer. |

## Review criteria

- Question relevance: does the answer address the actual question?
- Evidence support: can each advice claim be traced to the retrieved text?
- Age suitability: are the returned references eligible for the profile age?
- Practicality: are the actions understandable and feasible?
- Scope: does the answer avoid unsupported diagnosis, medication, or unrelated advice?
- Timing: record retrieval and generation time separately from browser/audio latency.

For each criterion, record supported, concern, or not assessed with a short reason.
Do not infer relevance from similarity scores or treat this small development sample
as a percentage accuracy score. These examples are not a held-out evaluation set.

## Results

Configuration: `gemini-3.8-flash`, Qdrant collection `caregiver_guidance_minilm_v1`,
evidence threshold `0.50`, completed age six months / 183 days. Base revision: `3d4b017`.

The initial generation run and the subsequent retrieval-only inspection were separate
requests. Scores below come from the retrieval-only inspection. They are similarity
scores, not accuracy or expert relevance labels.

### cq01: play

| Retrieved passage | Source page | Age label | Score | Gate |
| --- | --- | --- | --- | --- |
| `dc2672fee5b87f6db588` — 2. Play with Ball | Reach Up, 9 | 6–8 months | 0.6792 | accepted |
| `29aec435a4fd90abbd87` — How to use play activities | Reach Up, 32 | 0–24 months | 0.6284 | accepted |
| `65c6ccc51e6267c73511` — child not responding or seems slow | CCD, 3 | 0–24 months | 0.5735 | accepted |

- Retrieval relevance: concern. The first two passages address the question. The third
  introduces a developmental concern that was not stated in the question.
- Age eligibility: supported for the selected profile; this is not clinical validation.
- Generated answer: not assessed. Gemini returned `ServerError`, HTTP 503.
- Answer support, practicality, and answer scope: not assessed because no answer returned.
- Timing: not captured for the failed request; no latency claim is made.

### cq02: communication during feeding

| Retrieved passage | Source page | Age label | Score | Gate |
| --- | --- | --- | --- | --- |
| `5d58aed9ded439496279` — Talk with baby during feeding time | Reach Up, 41 | 6–8 months | 0.7969 | accepted |
| `b7f13e95fec7eb520e4c` — not breastfeeding: responsive feeding | CCD, 3 | 0–24 months | 0.6459 | accepted |
| `f2a95a5820094bf198f7` — Talk with your children | Reach Up, 34 | 0–24 months | 0.6273 | accepted |

- Retrieval relevance: supported at an initial text-review level. The excerpts address
  talking, responding, and interaction during feeding. The non-breastfeeding passage has
  a specific context that should not be assumed for every caregiver.
- Age eligibility: supported for the selected profile; this is not clinical validation.
- Generated answer: not assessed. The request remained pending for several minutes and
  the synthetic evaluation process was stopped. No HTTP error or exact duration was
  captured for this case; it is incomplete, not a failed answer-quality score.
- Answer support, practicality, and answer scope: not assessed.

### cq03: unrelated car-repair question

Retrieved scores were `0.1750`, `0.1720`, and `0.1682`; all were below `0.50`.
The outcome was `no_evidence`, with no generation call in this check.

Actual response:

> I couldn't find suitable guidance for this question in the available references.
> Try rephrasing it. For health or development concerns, contact a health worker.

- Scope: supported for this example. No automotive instructions were generated.
- Timing: 2.542 seconds for retrieval and the gate check; not browser end-to-end latency.

## Findings and next actions

1. The score threshold does not guarantee question relevance: cq01 admitted an
   age-eligible passage about a concern absent from the question.
2. Retrieval completed, but the generation service returned a 503 or remained pending.
   Investigate generation availability and bounded request timeouts before rerunning
   answer-quality checks. Do not tune the threshold based on these service failures.
3. Rerun the two caregiving cases after generation is available, retain the actual
   answers, and review each claim against the supplied excerpts.
4. Three development examples do not establish overall quality, safety, or accuracy.

## Follow-up implementation: generation waiting

The Gemini client previously set no explicit request timeout. The installed SDK converts
an unset timeout to `None` for the underlying HTTP request. This is a plausible contributor
to prolonged waiting, not proof of the cause of the remote 503.

Added `GEMINI_TIMEOUT_SECONDS` (default 30, supported range 1–120) and one request attempt
without automatic retries. Network timeout exceptions during generation produce HTTP 504
with a retry message and do not save a fabricated answer or no-evidence outcome.
Retrieval failures retain their separate error behaviour.

The timeout is a network-operation setting, not a strict wall-clock deadline for the
complete retrieval/generation/storage pipeline. It does not establish compliance with
the 3.5-second latency target.

## Timeout verification and live retry

The initial timeout configuration and endpoint checks completed with 21 tests passing
and two dependency deprecation warnings. The two fixed caregiving questions were then
retried using a fresh service instance with a 30-second timeout and one attempt.

| Case | Retrieval (seconds) | Generation (seconds) | Total (seconds) | Actual outcome |
| --- | --- | --- | --- | --- |
| cq01: play | 2.159 | 30.592 | 32.752 | SDK ServerError, HTTP 504; no answer |
| cq02: feeding | 1.378 | 29.032 | 30.410 | SDK ServerError, HTTP 504; no answer |

The same passage IDs and rounded scores listed above were retrieved in the retry.
Both requests completed without manual termination. These timings cover direct service
calls, not the authenticated browser flow, Firestore writes, transcription, or TTS.
No new answer-quality rating is possible because neither generation request returned text.

The SDK returned its own HTTP 504 exception rather than a transport timeout. A follow-up
change maps that exception to the same timeout response handled by the coaching API.
Other API errors, including HTTP 503, retain their service-failure classification.
Two additional regression cases cover this distinction. Verification completed with
23 tests passing and two dependency deprecation warnings in 5.81 seconds:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_coaching_service.py tests/test_evidence_gate.py
```

Generation availability remains unresolved. Do not increase the timeout or change the
model solely to turn a service failure into a passing quality result; first inspect
availability and configuration separately from retrieval relevance.

Direct service checks do not verify login, Firestore persistence, microphone recording,
browser rendering, or audio playback. Those require separate browser checks.
