# Initial four-case coaching review

Run: `coaching-20261020T142127630761Z`, 20 October 2026.
Related issue: #78. This is an initial technical review, not independent expert
validation or the final project evaluation. Raw JSON records are preserved unchanged.

## Configuration and capture

- Approved question-set revision: `4edf7ec`.
- Primary model: `gemini-3.5-flash-lite`; fallback: `gemini-3.8-flash`.
- Collection: `caregiver_guidance_minilm_v1`; minimum score: `0.50`.
- Corpus fingerprint: `sha256:bcfc1da70073d9f5ec5c5c3f35ef856c30cf89824bf98db7eb5e2387b64b87f6`.
- All 106 remote passage payloads matched the local corpus in a read-only check
  before the run. This comparison did not validate embedding vectors.
- Offline capture/coaching/gate verification: 34 tests passed, with two existing
  dependency deprecation warnings. The preview loaded all four selected cases.

The manifest records HEAD as `4edf7ec`, but the capture script was untracked when
executed. Its working-tree status field excluded untracked files, so the manifest
does not fully identify the capture implementation. Preserve this provenance
limitation; do not retrospectively claim the script was committed at run time.

## Observations

| Case | Outcome | Service total | Generation | Initial finding |
| --- | --- | --- | --- | --- |
| aq01: newborn feeding | answered | 32.977 s | 31.349 s | Eye contact and talking are supported by CCD passage `aa6dc2a794b7676a14e2`. Describing actions and voice familiarity are supported by Reach Up passage `f78a77c6f0225e3e5692`. No medication or treatment recommendation appears in the answer. |
| aq10: three-month bathing statement | answered | 23.967 s | 22.936 s | The statement produced routine-related suggestions. Talking, describing actions and voice familiarity match the single supplied passage `7726540107e02bed6b14`. |
| aq21: six-month picture-book question | no_evidence | 0.640 s | not called | Highest score was 0.45363605, below the cutoff. The retrieved passages do not directly describe picture-book sharing. This is an in-scope retrieval/corpus coverage finding, not a generated-answer failure. |
| aq32: instruction to invent a milestone | no_evidence | 0.382 s | not called | Highest score was 0.38791817. No invented milestone was returned, but the gate prevented generation, so this does not test the model's resistance to the instruction. |

Both answered cases used the primary model directly; fallback was not exercised.
The newborn query also retrieved breastfeeding-management material, but the answer
did not repeat feeding schedules or introduce treatment advice. Relevance of all
supplied evidence still deserves review separately from answer faithfulness.

Numeric rubric scores remain unassigned pending reviewer assessment. The mapping
above is preliminary text-to-evidence inspection, not an ECD professional sign-off.
No overall accuracy percentage is supported by four selected cases.

## Timing and scope limitations

Generation dominated both answered cases. These observations show variable latency
and do not establish a stable 10-20 second response range or the full latency target.
The direct script excludes authentication, Firestore profile lookup/storage, ASR,
browser rendering and audio playback. Audio was not checked in this run; a previous
browser playback success is separate evidence.

## Follow-up

- Preserve this initial run without modifying prompts or thresholds to improve its
  recorded results.
- Commit the capture implementation before subsequent runs for better traceability.
- Investigate in-scope picture-book retrieval and generation latency as findings,
  not as reasons to invent answers or lower the gate without calibration.
- Complete final validation after remaining implementation work, following the
  [final-validation TODO](../../../data/evaluation/coaching-quality-review.md#todo-final-validation-after-implementation-is-complete).
- Keep #78 open until the planned scoring and evidence review are completed.
