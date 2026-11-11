# Parenting Voice Assistant v0.2.0

Released 2 November 2026. [Open LittleCare](https://littlecare.app).

This release brings the caregiver workflow to a hosted HTTPS application and
includes the conversation, safety, privacy and personalization changes since
[v0.1.0](https://github.com/Vinit-Rabadiya/parenting-voice-assistant/releases/tag/v0.1.0).
The tagged v0.1.0 documentation remains available with that release.

## Highlights

- Email/password and Google sign-in with email verification, optional authenticator
  MFA, backup authenticators and account security settings.
- Private child profiles with calculated age, milestones and optional health-and-care
  notes. Enabled notes and care instructions can inform replies without interpreting
  test results or treating saved notes as verified clinical evidence.
- One composer for typed messages and editable English transcripts, Enter to send,
  Stop waiting, saved conversation history and child-specific conversation context.
- Baby-care questions, statements and follow-ups for birth through 24 months,
  supported by 216 selected source-linked passages and broader in-scope guidance.
- Kenya vaccination education and callable emergency contacts with safety routing.
- Listen/Stop and an account-specific automatic-playback preference in the browser.
- Five-point feedback with optional reasons/comments and an administrator dashboard.
  Private chats and child profiles are not available to administrators.
- Docker packaging, private image publishing and Standard Consumption hosting at
  `littlecare.app` with an Azure-managed HTTPS certificate.

## Requirements and operation

The application uses React, FastAPI, pretrained faster-whisper, Firebase
Authentication, Firestore, Qdrant and Gemini. The default speech model is `base`,
configured for English. Generation defaults to `gemini-3.5-flash-lite` with a
configurable fallback. These model settings remain configurable after deployment.

[README.md](README.md) is the project entry point. The
[setup guide](docs/setup.md) contains detailed environment and service instructions.
Use [.env.example](.env.example) for configuration names and
[data/README.md](data/README.md) for source preparation and collection requirements.
Service credentials, source PDFs and generated indexes are not release attachments.

The hosted application runs as `littlecare-app` in `parenting-voice-rg`, Switzerland
North. Start it before use and stop it after a session using Azure's Overview page.
It is unavailable while stopped. Budget alerts do not stop spending; logs and other
stored resources can incur charges independently of running compute.

GitHub Actions publishes checked main images to private GHCR. Automatic Azure
updates are not enabled until the Azure deployment identity and repository settings
are configured. A release tag does not itself update the running container.

## Deployment modes and retention

The current operating guidance distinguishes a controlled demonstration from a
real-caregiver pilot. These notes describe the intended use; the running flags,
provider accounts, billing, backup settings and deployed commit were not verified
in this documentation update.

- **Demo:** use fictional child profiles, notes and non-personal example messages,
  including earlier chat context. A provider's non-personal-testing flag records
  the operator's assertion; it does not anonymize input or prevent real details
  from being entered.
- **Pilot:** review the actual provider account and processing arrangements before
  accepting real caregiver data. Confirm Gemini paid-service processing or Groq
  data terms as applicable, independently for every enabled failover provider.
  Match the notice and its version to the processing; changing a confirmation
  flag alone does not obtain new consent or verify billing.
- **Retention:** stored caregiver records have no automatic expiry. Application
  deletion removes the relevant Firestore data; account deletion also removes the
  login account. Provider records, hosting logs and backups have separate settings
  and are not erased by those app controls.

See [deployment modes and provider requirements](docs/deployment.md#deployment-modes)
and [the retention statement](docs/privacy.md#retention-and-deletion).

## Speech evaluation status

The current development tooling can measure the unchanged pretrained English
speech model against local reference recordings. Generic fixture runs verify the
evaluator; accuracy on Kenyan-caregiver speech and its retrieval impact remain
unmeasured. New participant recordings are optional: an appropriately licensed
existing dataset is another evaluation route. See
[evaluation status](docs/evaluation.md#speech-evaluation-status) and
[the speech protocol](eval/stt/README.md). No fine-tuning or live request-path
change is introduced by this offline evaluator.

## Scope and availability

- Kenya is the current supported country, and children must be within birth through
  24 months. Guidance uses the selected profile age or an explicitly clarified
  conversation age; it does not silently change the saved date of birth.
- English transcription can misrecognize wording and accents. Review the transcript
  before sending. Kiswahili and mixed-language recognition are not supported in this
  release. Browser speech voices and autoplay behavior vary by device.
- The current development build keeps voice transcription fixed to English and
  checks submitted text locally before coaching generation. Unsupported or uncertain text receives a
  fixed English/Kiswahili boundary message. Language identification is imperfect;
  this does not provide Kiswahili coaching or validate medical safety.
- Generated guidance can contain errors. Retrieved citations support review but do
  not verify every generated claim. The application does not diagnose, prescribe,
  interpret test results or confirm an individual child's vaccination doses.
- Urgent routing and Kenya contacts assist access to professional help; the rules
  are not a complete or clinically validated emergency assessment.
- Versioned consent and ownership checks protect access to saved data. Enabled
  profile context and submitted text are processed by external services as described
  in the privacy notice. Free-tier model processing is configured only for confirmed
  non-personal testing; deployment does not remove provider data-handling conditions.
- Ratings and comments inform administrator review and subsequent tested changes.
  They do not automatically retrain or modify a model.
- Internet connectivity, service quotas and provider demand affect response times.
  No fixed response-time or complete baby-care coverage guarantee is made.
- Backend web search and voice-controlled actions remain optional future work.

## Verification

`npm.cmd run check` passed on 2 November 2026: 1,218 backend tests, 238 frontend
UI tests, seven audio tests, Python/frontend lint and the production frontend build.
Backend, frontend and lockfile versions agree on 0.2.0. The hosting template passed
JSON and Azure deployment validation during the domain transfer.

On 2 November 2026, hosted checks passed for trusted HTTPS, frontend JavaScript,
`/api/health/live` (200), unauthenticated `/api/me` (401), and HTTP-to-HTTPS redirection.
Google sign-in and opening the chat screen also passed manually at `littlecare.app`.

The earlier signed-in conversation checks W1–W8 and playback checks P1–P4 passed.
They cover recording/editing, follow-ups, saved history and feedback, cancellation,
child isolation, deletion and playback settings. They are recorded separately from
the hosted smoke checks in
[conversation acceptance #66](https://github.com/Vinit-Rabadiya/parenting-voice-assistant/issues/66)
and [playback acceptance #75](https://github.com/Vinit-Rabadiya/parenting-voice-assistant/issues/75).

Automated checks use test doubles for external services where appropriate. They do
not establish clinical effectiveness, complete safety coverage or transcription
accuracy across Kenyan accents. Source and response evaluation records are linked
from [data/README.md](data/README.md).
