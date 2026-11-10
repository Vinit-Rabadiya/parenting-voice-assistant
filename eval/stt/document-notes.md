# Speech evaluation text for the project document

## Current status: evaluation prepared, caregiver measurements pending

LittleCare uses the pretrained multilingual Whisper `base` model through
faster-whisper, configured to transcribe English on CPU using INT8. The model has
not been fine-tuned. An offline evaluation runner has been prepared to measure
word error rate, transcription time, real-time factor and optional retrieval
changes against verified reference transcripts. No Kenyan-caregiver recordings
have yet been collected; therefore no population or caregiver-domain accuracy
claim is made. A generic audio smoke test is separate implementation evidence.

## Methodology outline for the completed study

Record the actual date, participant selection, number of speakers, number of
clips, devices, recording conditions, participant agreement and reference-checking
procedure. Describe the study as read speech if participants read supplied
prompts. State any deviations from the planned five speakers and forty clips.
Do not describe repeated inference as additional recordings or participants.

The evaluator calls the same English-only speech service as the application.
One warm-up transcription per model is excluded from measured results. Word error
rate is pooled from substitutions, deletions and insertions divided by reference
words. Scoring uses the first measured output per clip. Repeated runs provide
latency and stability measurements. Describe normalization, including the fact
that numeric digits and spoken number words are not made equivalent.

Separate transcription speed from the time to receive or hear a coaching answer.
Include the machine, CPU threads, model snapshot, dependency versions and audio
fingerprints from the actual report. Do not report a rounded or assumed model
version solely as `base` when a snapshot identifier is available.

## Results table to fill from a real caregiver run

| Model | Unique clips | Speakers | WER | Median transcription (s) | P95 (s) | Real-time factor | Retrieval change rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| base | Pending | Pending | Pending | Pending | Pending | Pending | Not measured |

If other models are compared, add rows for their measured runs on the same data.
Include speaker and noise-condition tables from `report.md`. Explain important
negation, age, local-food and symptom errors using anonymized examples. A changed
retrieved passage is not automatically an incorrect answer; unchanged retrieval
does not prove the answer is safe.

## Limitations to retain

This is a small convenience sample of English read speech, not all Kenyan
caregivers or all accents. Noise labels describe observed conditions without a
calibrated noise measurement. Reference quality, numeric orthography and device
characteristics affect WER. Local warm inference timing does not establish
production latency. No clinical validation follows from ASR measurements.

Use a generic smoke-test table only in a tooling-validation section, labelled
with its actual source and sample size. Do not copy its scores into the caregiver
results table or describe them as Kenyan-accent accuracy.
