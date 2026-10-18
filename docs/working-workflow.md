# Working coaching workflow

## What the application now demonstrates

An authenticated caregiver can create, update, and switch a private child profile;
record a question or type one; review the resulting transcript; request age-aware
coaching; see source citations; listen to the answer in the browser; and submit
feedback. Child profiles and interaction/feedback records are written through the
FastAPI backend to the authenticated user's Firestore path.

The response model is retrieval-augmented generation, not a fine-tuned LLM. The
backend sends Gemini only the age, routine, caregiver question, and retrieved
source passages. The prompt prohibits diagnoses, medication, doses, and unsupported
claims. Browser `speechSynthesis` supplies voice output for the current working
workflow.

## Data flow

```text
React input (typed or recorded)
  -> Whisper /speech/transcribe for recorded audio
  -> React transcript editor
  -> FastAPI /coach
  -> Firestore child profile -> server-calculated age
  -> Qdrant retrieval -> Gemini grounded answer
  -> Firestore interaction log
  -> React answer, sources, feedback, browser speech playback
```

## Manual verification record

Use this table during testing. Record actual timings rather than assuming the
3.5-second target, especially because cloud retrieval and generation depend on the
network.

| Scenario | Expected result | Actual result | Correction if needed |
|---|---|---|---|
| Create child | Profile persists and shows calculated age/milestones |  |  |
| Switch child | Guidance shows the selected child's age |  |  |
| Typed question | Answer appears with source links |  |  |
| Voice question | Transcript can be edited before submission |  |  |
| Listen | Browser reads the answer aloud |  |  |
| Feedback | Helpful/not helpful choice persists |  |  |
| Unsupported topic | Safe no-guidance message or health-worker direction |  |  |

## Automated verification completed on 18 October 2026

These checks preceded the later optional-milestone, theme, and Gemini-model changes;
they are a historical checkpoint, not verification of every change in this branch.

- Python lint: passed.
- Python tests: 114 passed.
- Frontend lint: passed.
- Frontend audio tests: 7 passed.
- Frontend UI tests: 63 passed.
- Frontend production build: passed.
- RAG corpus build: 106 source-linked passages prepared and uploaded to Qdrant.

The Python test run reports two dependency deprecation warnings from Starlette's
test client. They do not represent application test failures.

## Setup needed before manual testing

1. Add `GEMINI_API_KEY` to the root `.env`; optionally set `GEMINI_MODEL`.
   The current default is `gemini-3.8-flash`, selected after the provider rejected
   `gemini-2.5-flash` for new users. Restart the backend after changing environment settings.
2. Ensure the Firebase project has Firestore enabled and the existing Admin SDK key
   can access it.
3. Install the new backend dependency, then start the backend and frontend.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm.cmd run dev:frontend
```

The backend continues to require the project's verified Firebase account and TOTP
sign-in before it exposes child or coaching routes.
