# Changelog

## 0.2.0 — 2 November 2026

### Added

- Persistent conversations with child-specific history, follow-up context, deletion,
  immediate message submission, Enter to send and cancellation feedback.
- Optional TOTP MFA, backup authenticators, account security settings, versioned
  privacy consent, usage information and account/profile deletion controls.
- Saved milestones and optional health-and-care notes used as context for tailored
  replies when enabled. Notes remain caregiver-provided information, not verified diagnoses.
- Kenya vaccination education, callable emergency contacts, input/output safety
  checks and broader everyday baby-care references for birth through 24 months.
- Five-point helpfulness ratings, optional reasons/comments and an administrator
  feedback dashboard that does not expose private conversations or child profiles.
- Local Whisper `base` transcription for English recordings, editable transcripts,
  cleaned speech playback and a compact automatic-playback preference.
- Container packaging, private GHCR image publishing, deployment controls and
  Standard Consumption hosting with managed HTTPS at `littlecare.app`.

### Changed

- Expanded the selected reference collection from 106 to 216 source-linked passages.
- Defaulted generation to configurable `gemini-3.5-flash-lite`, with a separate
  fallback model and bounded provider handling.
- Improved age clarification, topic continuity and requests phrased as statements.
  Missing references alone no longer prevent an in-scope response.
- Consolidated recording and typed text into one chat composer and improved profile,
  conversation and account menus.
- Updated dependencies, deployment validation, credential exclusions, diagnostics
  and HTTP security headers.

### Verification and scope

- Full checks passed on 2 November 2026: 1,218 backend tests, 238 frontend UI tests,
  seven audio tests, both linters and the frontend production build.
- Hosted smoke checks on 2 November 2026 verified trusted HTTPS, the frontend and
  JavaScript, health HTTP 200, protected account HTTP 401 and HTTP-to-HTTPS redirection.
  Google sign-in and opening the chat screen passed manually on `littlecare.app`.
- Earlier signed-in W1–W8 conversation checks and P1–P4 playback checks passed;
  these are separate from the hosted smoke checks. See
  [conversation acceptance](https://github.com/Vinit-Rabadiya/parenting-voice-assistant/issues/66),
  [playback acceptance](https://github.com/Vinit-Rabadiya/parenting-voice-assistant/issues/75)
  and [release notes](RELEASE.md).
- English speech recognition can make errors. Guidance and safety rules are not
  clinically validated and do not replace professional care. Feedback does not
  retrain models automatically. Web search and voice-controlled actions are optional
  future work. Azure automatic image updates require separate identity configuration.

## 0.1.0 — 19 October 2026

Initial release of the caregiver coaching workflow.

### Added

- Firebase account registration, email verification, and authenticator sign-in.
- Private Firestore child profiles with create, edit, and switch controls, date of
  birth, calculated age, baseline milestone display, and optional additional milestones.
- Typed questions and browser voice recording with local Whisper transcription
  after recording stops. Caregivers can edit transcripts before submission.
- Qdrant retrieval of age-matched reference passages with optional routine context.
- Gemini coaching responses with displayed source titles, pages, and links.
- Browser speech playback with Listen/replay and Stop controls.
- Stored interactions and Helpful/Not helpful feedback with optional comments.
- A 106-passage source-linked corpus and generated coverage counts by source age
  label, topic, and routine.
- Coaching and profile panels follow the application's light/dark theme.

### Changed

- Set `gemini-3.8-flash` as the default coaching model, configurable through
  `GEMINI_MODEL`.
- Provider diagnostics identify the failing service while redacting credentials
  and submitted content from the additional error description.

### Fixed

- Updated recording instructions to describe submitting edited transcripts for guidance.

### Verification

On 19 October 2026, `npm.cmd run check` passed for the prepared 0.1.0 version:
114 Python tests, 63 React tests, 7 audio tests, Python/frontend lint, and the
frontend production build. Two
dependency deprecation warnings remain in the Python test-client stack.
These checks verify the existing test coverage; they do not establish all release
features or outstanding safety requirements as fully tested. Manual verification
also confirmed coaching response generation and spoken output.

See [RELEASE.md](RELEASE.md) for setup requirements, scope, and availability.
