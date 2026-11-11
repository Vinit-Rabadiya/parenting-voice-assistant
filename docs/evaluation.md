# Evaluation status and evidence

[Documentation home](../README.md#documentation).

## What the existing checks establish

| Evidence | Status | Practical limit |
| --- | --- | --- |
| Backend/frontend checks | Run through `npm run check`; CI runs its configured checks on changes | Test doubles and implementation regression tests are not clinical validation |
| Child-danger routing | Fixed 60-case development set with a CI recall/false-alarm gate | Cases were used during development; results do not establish real-world sensitivity |
| Language boundary | Fixed 43-case development set using the real offline detector | Selected English, Kiswahili and mixed-language examples do not cover every language or code-switch |
| Retrieval | Labelled pools, age checks and recorded evaluation runs | Report the recorded corpus/configuration and split; project-authored labels are not independent review |
| Answer quality | Editorial source/answer reviews and recorded corrections | These are not qualified independent clinical or ECD approval |
| Signed-in workflow | Historical acceptance records and automated React-to-API checks | Hosted smoke checks and local test doubles establish different things |
| Speech tooling | Offline WER/speed evaluator, tests and generic fixture smoke runs | A pretrained model and a successful fixture do not measure Kenyan-caregiver accuracy |
| Representative speech accuracy | Not measured on a Kenyan-caregiver sample | Requires appropriate existing audio/references or voluntary evaluation recordings |
| Qualified expert validation | Not yet completed in repository evidence | Prepared review samples are not completed expert ratings |

See [safety evaluation](../eval/README.md),
[retrieval and coverage review](../data/evaluation/coverage-development-review.md),
[answer-quality review](../data/evaluation/coaching-quality-review.md),
[release verification](../RELEASE.md#verification) and
[performance evidence](../PERFORMANCE_REPORT.md). Their dates, model settings,
denominators and stated limitations apply to each recorded result.

## Speech evaluation status

LittleCare uses pretrained Whisper `base` through faster-whisper, with English
transcription, CPU INT8, bounded decoding and no fine-tuning. The optional
`scripts/evaluate_speech.py` calls this unchanged service outside the application
request path. It reports WER, transcription time, real-time factor and optional
raw retrieval changes, with model snapshots, audio hashes and run metadata.

The existing generic JFK fixture has been exercised locally. Those runs validate
the evaluator and describe that fixture on the recorded machine. They do not
measure Kenyan accents, caregiver vocabulary or household noise. No retrieval
change was measured in the default local smoke runs. Do not present a missing
metric as zero or copy fixture WER into a caregiver-accuracy table.

Collecting new recordings is optional. An appropriately licensed existing dataset
with reference transcripts can also support evaluation. The prepared five-speaker,
40-clip pack is a suggested study design, not a technical prerequisite for running
the application. Until representative evaluation is performed, state that target
speech accuracy remains unmeasured.

Use the [speech protocol](../eval/stt/README.md),
[document-ready status and method notes](../eval/stt/document-notes.md), and
[collection template](../eval/stt/manifest.template.jsonl). Local detailed results
are git-ignored because recordings and transcripts can contain participant data.

## Wording for the project document

> LittleCare uses a pretrained English-configured speech recognition model without
> fine-tuning. An offline accuracy and speed evaluation method has been implemented
> and checked with a generic fixture. Recognition accuracy on Kenyan caregivers
> has not yet been measured. Retrieval and answer-quality results are reported for
> their recorded datasets and configurations; they do not establish clinical
> effectiveness or independent professional validation.

No automatic model change, per-account usage cap or additional live evaluation
request is introduced by these documentation or offline evaluation tools.
