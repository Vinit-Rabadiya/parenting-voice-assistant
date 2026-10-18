# Changelog

## 0.1.0 (Unreleased)

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
