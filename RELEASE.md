# Parenting Voice Assistant 0.1.0

Initial release of the caregiver coaching workflow. Publication pending.

Version 0.1.0 connects child profiles, voice and text input, source-based coaching,
and spoken responses in a local web application.

## Highlights

- Create, edit, and switch between child profiles with birth dates, calculated
  ages, and optional milestone entries.
- Type a question or record English speech, then review and edit the transcript.
- Request coaching using the selected child's age and an optional routine.
- Read generated guidance alongside reference titles, page numbers, and source links.
- Listen to responses with browser playback controls.
- Save interactions and submit Helpful/Not helpful feedback with optional comments.
- Retrieve guidance from a selected collection of 106 source-linked passages.

## Requirements and setup

The application uses React, FastAPI, local Whisper transcription, Firebase
Authentication, Firestore, Qdrant Cloud, and Gemini. Internet access and configured
service credentials are required. Browser recording requires microphone permission
and localhost or HTTPS; available playback voices vary by browser and device.

Use the setup instructions in [README.md](README.md) and
[the workflow guide](docs/working-workflow.md). Enable Cloud Firestore API and
create the default database. Configure the backend using [.env.example](.env.example);
the default coaching model is `gemini-3.8-flash`. Qdrant must contain the prepared
corpus. Source documents and generated corpus files are not bundled with the repository.

From the repository root, start the backend and frontend in separate terminals:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd run dev:frontend
```

Open http://localhost:5173/ and complete email verification and authenticator sign-in.

## Scope and availability

- Guidance focuses on caregiver-child interaction from birth through 24 months,
  using selected developmental reference resources.
- Voice input supports English, with an editable transcript available after
  recording stops. Recognition quality depends on speech and recording conditions.
- Internet access is required for authentication, stored profiles, retrieval,
  and answer generation. Service availability and quotas can affect response times.
- Spoken playback uses browser and operating-system voices, which vary by device.
- Generated guidance may contain errors or omit relevant information. Source links
  support review; they do not guarantee the accuracy of every generated claim.
  The application provides developmental coaching rather than medical diagnosis,
  treatment, or emergency assessment.
- Profiles, questions, responses, and feedback are stored in Firestore. Question
  text is processed by Qdrant Cloud and Gemini; Gemini also receives retrieved
  reference passages and child age. In-app consent, retention information, and
  account-data deletion controls are not available in this version. Use fictitious
  profiles for evaluation.

## Verification

On 19 October 2026, all configured checks passed: 114 Python tests, 63 React tests,
7 audio tests, Python/frontend lint, and the frontend production build. Two
dependency deprecation warnings remain in the Python test-client stack.

Manual verification confirmed coaching generation and spoken output. These results
reflect existing test coverage and do not establish complete end-to-end, clinical,
or safety validation.
