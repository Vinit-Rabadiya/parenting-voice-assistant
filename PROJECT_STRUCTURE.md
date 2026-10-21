# Project structure

Use [README.md](README.md) for installation, configuration, API routes, and data
handling. This guide maps the implementation without duplicating setup details.

## Backend

| Location | Responsibility |
| --- | --- |
| `backend/main.py` | FastAPI application, Firebase startup, shared speech model, transcription capacity limit, and shutdown. |
| `backend/api/v1/router.py` | Registers health, account, speech, children, coaching, and conversation routes. |
| `backend/api/dependencies.py` | Provides shared services; coaching, retrieval, and data services initialize on demand. |
| `backend/core/config.py` | Loads application and service settings. |
| `backend/core/firebase.py`, `security.py` | Firebase Admin initialization and authenticated access requirements. |
| `backend/schemas/` | API request and response validation. |
| `backend/services/age.py` | Calendar age and birth-through-second-birthday scope. |
| `backend/services/caregiver_data.py` | Per-account Firestore profiles, conversations, feedback, legacy interactions, and deletion. |
| `backend/services/audio_validation.py`, `speech.py` | WAV validation and local Whisper transcription. |
| `backend/services/retrieval.py`, `evidence.py` | Qdrant retrieval, age/routine eligibility, and relevance threshold selection. |
| `backend/services/conversation_context.py` | Bounded recent exchanges and caregiver context for explicit follow-up searches. |
| `backend/services/coaching.py` | Evidence-grounded prompts and generation-model requests. |
| `backend/services/input_safety.py`, `crisis_safety.py`, `response_safety.py` | Input and output checks and supported safety outcomes. |

Routes are mounted at the root and under `/api/v1`. Vite forwards the development
frontend's `/api` requests to root backend routes.

## Frontend

| Location | Responsibility |
| --- | --- |
| `frontend/src/main.jsx` | Mounts React with development StrictMode checks. |
| `frontend/src/App.jsx` | Selects home, authentication, and account screens. |
| `frontend/src/context/` | Shared authentication state. |
| `frontend/src/pages/AccountPage.jsx` | Verification, authenticator setup, and account deletion. |
| `frontend/src/pages/AuthPage.jsx` | Sign-in, registration, and MFA challenges. |
| `frontend/src/pages/LandingPage.jsx` | Guest entry and authenticated workspace. |
| `frontend/src/components/GuidanceWorkspace.jsx` | History, message thread, shared composer, and cancellation controls. |
| `frontend/src/components/GuidanceAnswer.jsx` | Answer outcomes, expandable sources, browser speech playback, and feedback. |
| `frontend/src/components/ChildProfiles.jsx` | Profile picker and add, edit, and detail dialogs. |
| `frontend/src/components/MicrophoneControls.jsx` | Connects recording and transcription to the editable message. |
| `frontend/src/hooks/useConversations.js` | History loading, submission, deletion, and request lifecycle. |
| `frontend/src/hooks/useMicrophone.js`, `useTranscription.js` | Capture resources, audio preparation, transcription, and cancellation. |
| `frontend/src/hooks/useAccountAccess.js` | Backend-verified account access state. |
| `frontend/src/services/` | Authentication and API requests. |
| `frontend/src/utils/audio.js` | Merging, resampling, and WAV encoding. |
| `frontend/public/audio/capture.worklet.js` | AudioWorklet microphone sample capture. |

## Main request flow

1. Typed input enters the shared composer. Recorded input passes through audio
   capture, WAV preparation, `/speech/transcribe`, and the same composer.
2. Sending adds the message to the visible thread. `useConversations` creates a
   conversation when needed and submits through `caregiving.js` to `/coach`.
3. The backend verifies access, loads the owned child profile, and checks safety
   and age scope. Safety outcomes can bypass retrieval and generation.
4. Eligible requests load bounded context, retrieve age-aware references, select
   evidence, generate guidance, and check the generated output.
5. The exchange is saved; the frontend displays the answer, sources, feedback,
   and optional browser speech playback.

New messages use `users/{uid}/conversations/{id}/messages/{id}`. Older standalone
interactions remain under `users/{uid}/interactions/{id}` and are not automatically
migrated into the history list.

## Data, scripts, and tests

- `data/`: source inventory, passage selections, and evaluation questions. See
  [data/README.md](data/README.md) for corpus preparation.
- `scripts/`: preparation, indexing, diagnostics, and evaluation entry points.
  These are not unused merely because the server does not import them.
- `tests/`: backend, data-pipeline, safety, and evaluation tests.
- `tests/frontend/`: React lifecycle/API tests and binary audio helper tests.
- `eval/`: cases and recorded evaluation evidence for its recorded configuration.
- `notebooks/`: exploratory audio work, separate from application runtime.
- `firestore.indexes.json`: conversation query index definition.

## Verification and dependencies

- `npm run lint`: Python and frontend lint only.
- `npm test`: Python and frontend tests only.
- `npm run check`: lint, tests, and production frontend build.
- `.husky/pre-push`: invokes the full local check.
- `.github/workflows/ci.yml`: backend/frontend jobs on pull requests and pushes
  to `main`, using Python 3.12 and Node.js 22.
- `requirements.txt`: runtime dependencies.
- `requirements-data.txt`: standalone data tooling dependencies.
- `requirements-dev.txt`: runtime, data tooling, lint, and test dependencies.
