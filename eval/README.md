# Safety evaluation

## Scope

The safety workstream covers the shared child-danger dataset and CI report (#59),
caregiver support routing (#57), and input/output check improvements (#58 and #42).
Professional review under
#79 and final guidance-quality scoring under #78 remain distinct external/final
validation activities, not implicit claims made by these checks.

Verification record:

- [x] Review the shared 60-case data file and report calculations.
- [x] Verify crisis/support routing, source information and explicit country selection.
- [x] Verify API, interface, persistence-failure and evaluation integration.
- [x] Review the implemented input/output rules and regression examples for false alarms,
  missed wording and source-card consistency; broader clinical validation remains separate.
- [x] Run offline checks and capture an actual report; record the code/data versions.
- [x] Run the full configured project checks locally.
- [x] Verify the backend CI evaluation step on GitHub.
- [x] Record remaining limitations and issue evidence.

## Shared data and report

`redflags.jsonl` contains the existing 30 danger reports and 30 non-emergency
examples, moved without changing their wording or labels from the original tests.
Each line is an object with `id`, `question`, `completed_months` and
`should_escalate`. These are selected development examples used when building the
rules, not independent evidence of real-world sensitivity or clinical validity.
Additional regression cases live in the test files and are not silently included
in the 60-case metric denominator.

Both Pytest and `scripts.evaluate_safety` read this dataset. They do not contact
Qdrant, Gemini, Firebase or a support service. The report captures the canonical
data fingerprint, code revision where available, counts and per-case outcomes.
Code revision alone does not identify uncommitted code; commit/review the final
implementation before recording final evidence.

Definitions:

- True positive: a labelled danger report was flagged.
- False negative: a labelled danger report was missed.
- False positive: a labelled non-emergency example was flagged.
- True negative: a labelled non-emergency example was not flagged.
- Recall = detected danger reports / all labelled danger reports.
- False-alarm rate = flagged non-emergency examples / all non-emergency examples.

The CI gate requires recall of 1.0 and a false-alarm rate of 0.0 **on this fixed
set only**. This is a regression requirement, not a promise that all real-world
emergencies will be detected. Invalid data or a missing case class is an error,
not a passing score. The two metrics are separate so that flagging every input
cannot produce a passing result.

Run offline tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_input_safety.py tests/test_response_safety.py tests/test_crisis_safety.py tests/test_safety_evaluation.py tests/test_evidence_gate.py tests/test_coaching_evaluation.py
```

Print a report without writing a results file:

```powershell
.\venv\Scripts\python.exe -m scripts.evaluate_safety --check
```

To save a report, add `--output` with a new path, for example
`--output eval/results/safety-development-report.json`. Existing reports are not
overwritten. GitHub runs the same command in the existing backend job and uploads
`safety-report.json` as the `safety-evaluation` artifact, even when the gate fails
after producing the report. No new CI job or live model call is required.

Initial verification completed with 166 Python tests and 67 frontend UI tests
passing, alongside frontend lint. The offline report printed 30 detected danger
examples, zero missed danger examples, zero false alarms and 30 correctly
unflagged non-emergency examples: recall 1.0 and false-alarm rate 0.0 on this
development set. Its dataset fingerprint was
`21315a4bc6afdef47106afb40cdb266971a48d1588b8c4d2c2f32d21f7789047`.
That initial run occurred before the implementation was committed and printed
rather than saved its report. A subsequent baseline is preserved separately in
[results/safety-baseline.json](results/safety-baseline.json), committed as `30e29c6`.
It identifies evaluated revision `dc47669ce63dc748ff04c16a2d82792b86e465b0`
and the same dataset fingerprint. Its 60 cases produced 30 detections, no missed
danger examples, no false alarms and 30 correctly unflagged non-emergency
examples. Recall was 1.0 and the false-alarm rate was 0.0 on this development set.

Manual browser checks completed for normal coaching, child danger-sign referrals,
a prevention question, caregiver support, immediate-support messages, contact
visibility with Kenya selected versus no location selected, and Listen/Stop audio.
The full `npm.cmd run check` subsequently completed with all configured checks
passed. Database-write failure behaviour was verified by automated tests, not by
forcing a production database outage during browser checks. GitHub Actions run
`39495077392` passed the backend safety evaluation and report-upload steps, alongside
backend and frontend checks. Professional clinical review remains outstanding. No real emergency response
or helpline connection was tested, and the baseline is not a claim of real-world
clinical accuracy.

## Caregiver support and resources

The support router separates possible self-harm/child-safety concerns from general
caregiver distress. It returns fixed messages without diagnosis or treatment.
Both routes bypass retrieval and generation. When child danger signs and caregiver
concerns coexist, urgent child-care wording takes priority while relevant caregiver
contacts remain available. Persistence failures do not suppress the response.

`support_country` is optional and currently accepts `KE` or null. The interface
defaults to no location selected. Kenya contacts appear only when Kenya is
explicitly selected. No US-only contact is substituted, no location is inferred
from the profile, and no call or safeguarding report is made automatically.
The interface shows each service's availability, information source and check date.
Contact availability is not checked in real time. A general local-healthcare
referral remains available when no supported location is selected.

Resource information was checked on 20 October 2026 using the local helpline
directory for Befrienders Kenya, the State Department for Children Services for
child protection, and the National Police Service for emergency contacts. Crisis
support phone details must be reverified through the helpline directory rather
than guessed from older project text. The checked date is not a guarantee that a
service can answer a particular call.

Sources for review:

- [Postnatal depression: symptoms and seeking professional help](https://www.nhs.uk/mental-health/conditions/postnatal-depression/)
- [Kenya child-protection services](https://childrenservices.go.ke/services)
- [Kenya National Police Service standards](https://www.nationalpolice.go.ke/sites/default/files/2025-01/NPS%20Service%20Standards.pdf)

Limits: English wording patterns can miss implicit intent, spelling errors,
historical context and unfamiliar phrases, and can flag non-emergency concerns.
The support response is not a depression diagnosis, suicide-risk assessment,
clinical triage or emergency service. Authentication and a selected, accessible
child profile remain prerequisites of the existing coaching interface. Service
availability, location support and clinical suitability need further review.
The output guard still checks patterns and source identity, not every claim's
semantic support. Numeric measurements can cause conservative false alarms.
