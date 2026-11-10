# English speech evaluation

This evaluates the existing pretrained speech model. No training recordings,
fine-tuning, application quota or request-path change is required. The runner calls
the same `SpeechService.transcribe(..., language="en")` used by the application.

## Current evidence

No Kenyan-caregiver recordings have been collected. The existing
`samples/samples_jfk.wav` is an 11-second generic fixture. Its separate smoke-test
report can demonstrate the runner and local timing, but cannot establish Kenyan
accent accuracy, caregiver-domain accuracy, noise robustness or model superiority.
Keep that distinction in the results chapter.

The [AfriSpeech-200 dataset](https://huggingface.co/datasets/intronhealth/afrispeech-200)
is a possible additional accented-English benchmark. Its dataset page currently
requires approved access and acceptance of its terms. No restricted audio was
downloaded. A licensed public benchmark would supplement caregiver recordings;
its domain, country selection, split and reference quality must be reported.

## Install and smoke-test the runner

Install the optional evaluation dependencies in the project environment. These
packages are not added to the application's runtime requirements or Docker image.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-speech-evaluation.txt
.\venv\Scripts\python.exe -m scripts.evaluate_speech eval/stt/smoke-manifest.jsonl --audio-root samples --dataset-kind smoke --dataset-label "Existing generic JFK fixture; not Kenyan caregiver speech" --models tiny.en base small --repeats 3 --output-dir eval/stt/results/jfk-smoke
```

macOS/Linux equivalent:

```bash
./venv/bin/python -m pip install -r requirements-speech-evaluation.txt
./venv/bin/python -m scripts.evaluate_speech eval/stt/smoke-manifest.jsonl --audio-root samples --dataset-kind smoke --dataset-label "Existing generic JFK fixture; not Kenyan caregiver speech" --models tiny.en base small --repeats 3 --output-dir eval/stt/results/jfk-smoke
```

Choose a new output directory for every run. The runner refuses to overwrite
results. It uses cached model files by default; `--allow-model-download` explicitly
permits downloading missing models. Default evaluation transcribes locally and
does not contact Firebase, Qdrant or a generation provider.

## Collection pack: five speakers, forty recordings

Use five adult volunteers who speak Kenyan-accented English. Record participant
agreement separately and use IDs `spk01` to `spk05`, without participant names in
filenames or reports. Use fictional caregiver questions; do not include a real
child's name, history or other personal details. This is evaluation, not training.

Each speaker records the eight prompts below once, for 40 distinct clips. The
manifest template alternates four quiet and four background-noise clips per
speaker. Background noise may be ordinary safe household sound; there is no need
to involve a child or deliberately cause distress. Note the actual recording
conditions and device in your study log. The labels are descriptive, not measured
noise levels. Let speakers use their natural accent and pace.

| Prompt | Fictional question |
| --- | --- |
| q01 | What foods can I give my six month old baby? |
| q02 | My newborn keeps crying after feeding. What can I try? |
| q03 | How can I help my nine month old baby settle at bedtime? |
| q04 | How do I make tummy time comfortable for my three month old baby? |
| q05 | My eight month old baby is teething. How can I comfort her? |
| q06 | Can I give uji and mashed beans to my twelve month old baby? |
| q07 | What should I do before preparing food for my baby? |
| q08 | My six week old baby has a fever and is not feeding. What should I do? |

Save mono, 16 kHz, 16-bit uncompressed PCM WAV clips, each no longer than 30
seconds, under `eval/stt/audio/spk01/q01.wav` and equivalent paths. The runner
uses the production audio validator and rejects incompatible files. Do not trim
words, change playback speed, denoise selected failures or remove hard examples
after seeing results. Record any uniform conversion/resampling method used.

Copy `manifest.template.jsonl` to `manifest.local.jsonl`. The template contains
40 planned rows and **does not assert that any recording or consent exists**.
For each completed recording:

1. Obtain agreement to use the recording, then set `usage_authorized` to `true`.
2. Listen and correct `reference` to exactly what was actually spoken. Do not
   obtain references from Whisper's own output. If the speaker paraphrases,
   score against their spoken words rather than the original prompt.
3. Have another listener check the reference where possible; set
   `reference_verified` to `true` only after verification. Record who checked it
   in a private study log. The flag itself does not establish independent review.
4. Correct `noise` if actual conditions differ from the plan. Keep all collected
   cases and explain exclusions before running the benchmark.

The audio folder, local manifest and detailed results folder are git-ignored.
Keep participant agreements and the identity-to-ID mapping outside the repository.
JSON reports contain reference and recognized text; inspect them before sharing.
Markdown reports contain aggregate tables without verbatim transcripts.

## Run the caregiver evaluation

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_speech eval/stt/manifest.local.jsonl --dataset-label "Five-speaker Kenyan English caregiver read-speech study" --models base --repeats 3 --output-dir eval/stt/results/caregiver-base-run01
```

To compare the existing alternatives on exactly the same clips, use
`--models tiny.en base small`. Keep `base` in production until the measurements
support a change. Comparing models does not retrain or configure the application.
Domain-prompt experiments are not included in this baseline.

Outputs are `report.json` (individual cases, transcripts, error counts, metadata)
and `report.md` (tables and method suitable for adapting into the document).
Reports contain the manifest and audio hashes, model snapshot identifiers,
package versions, CPU threads, platform, application source hash, evaluator hash,
Git revision and whether the workspace contained uncommitted changes.

## Optional retrieval-change measurement

The default run has no retrieval results; reports say **Not measured**, not zero.
To compare the reference and recognized text using the real Qdrant service:

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_speech eval/stt/manifest.local.jsonl --dataset-label "Caregiver study with raw retrieval comparison" --models base --repeats 3 --retrieval --date-of-birth 2026-05-10 --evaluation-date 2026-11-10 --output-dir eval/stt/results/caregiver-retrieval-run01
```

This option sends both texts to the configured Qdrant Cloud embedding/retrieval
service. Use only authorized fictional questions and a known collection revision.
No generation model is called. The evaluator computes the same exact day age and
completed calendar months from these fixed synthetic dates, disables retrieval
caching, and records collection/revision metadata. This is not an actual child.

The change rate is changed top-one passage IDs divided by clips whose reference
retrieved at least one passage. Missing-reference matches are reported separately,
and an entirely unmatched baseline yields **Not measured**, not 0%. Retrieval
failures abort the run rather than being counted as agreement. It compares raw
retrieval results, excluding evidence thresholds, local care facts, triage and
generation. It does not measure answer correctness or clinical effects.

## Metrics and reporting

- Pooled word error rate: `(substitutions + deletions + insertions) / reference
  words`. Long utterances contribute more reference words; this is not the mean
  of per-clip percentages. WER can exceed 100%.
- Accuracy uses the first measured transcript per unique clip. Additional repeats
  inform speed and stability, not additional independent speakers or recordings.
- Normalize both texts identically: NFKC, lowercase, contraction expansion,
  punctuation to spaces except decimal points, and whitespace collapse. Do not
  correct numbers, negation or domain terms. `six` and `6` remain different tokens;
  inspect such orthographic differences when interpreting WER.
- Report median and P95 transcription seconds and aggregate real-time factor
  (processing time divided by audio duration). Model loading and one warm-up clip
  per model are excluded and recorded separately.
- Report results by speaker and noise condition, with actual sample counts.
  Measurements exclude browser recording/upload, authentication, retrieval,
  generation, persistence and spoken playback. They are not hosted response time.
- Use the application baseline unchanged: English, CPU INT8, up to four threads,
  one worker, beam size 3, temperature 0, best-of 1, no preceding-text conditioning
  and VAD enabled. The source hash identifies the actual service implementation.

The read-speech convenience sample is small and does not establish performance
for all Kenyan accents, spontaneous caregiver wording or real household noise.
There is no automatic pass threshold, confidence interval or clinical approval.
Do not claim that an unmeasured retrieval change rate is zero.

For the document outline and honest current-status wording, see
[document-notes.md](document-notes.md). WER calculations use
[JiWER's documented word alignment](https://jitsi.github.io/jiwer/reference/process/).
