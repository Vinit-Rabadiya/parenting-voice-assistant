# Parenting Voice Assistant

A capstone project developing a voice- and text-based caregiver coaching system for **early childhood development (birth to 24 months)**. The intended assistant generates short, age-appropriate suggestions for language and cognitive stimulation during routines such as feeding, bathing, and play.

**Current stage:** the repository implements the authentication foundation and application skeleton. The developmental coaching, database, speech, retrieval, and model-training features are planned work.

## Current capabilities

| Area | Status |
| --- | --- |
| Email/password registration and login | Implemented with Firebase Authentication |
| Google sign-in | Implemented |
| Email verification and password-reset requests | Implemented |
| Authenticator-app MFA (TOTP) | Enrollment, QR code, and sign-in challenge implemented |
| Protected backend access | Firebase token verification, revocation check, verified-email and TOTP-session requirements |
| API health check | Implemented |
| Developer checks | Python lint/tests, frontend lint/build, pre-push hook, GitHub Actions |
| Child profiles and MongoDB persistence | Planned |
| Coaching workspace, history, and feedback | Planned |
| Generative coaching and ECD retrieval (RAG) | Planned |
| Speech-to-text and spoken responses | Planned |
| Dataset preparation, fine-tuning, and model evaluation | Planned |

The current UI contains authentication and account-setup screens. Installed dependencies such as `gTTS` and environment placeholders for AI providers do not yet represent integrated features.

## Architecture

### Implemented

```text
React + Vite
  ├── Firebase Authentication: login, verification, TOTP
  └── Firebase ID token → FastAPI → verified user ID
```

The browser calls `/api/me`. During development, Vite strips `/api` and forwards the request to FastAPI at `http://127.0.0.1:8000/me`.

### Planned coaching flow

```text
Caregiver voice or text
  → speech-to-text for voice input
  → question + selected child profile + caregiving routine
  → retrieve relevant ECD guidance
  → generative language model
  → coaching text + text-to-speech output
  → conversation history and feedback
```

The research direction is to compare a pretrained instruction model with a fine-tuned model, with and without retrieval. Fine-tuning teaches coaching behaviour; RAG supplies relevant reference material. This is a multi-component pipeline; a model ensemble would require a separately defined method for combining model outputs.

## Technology

- **Frontend:** React 19, Vite 8, JavaScript, Firebase Web SDK, QRCode.
- **Backend:** Python, FastAPI, Pydantic, Firebase Admin SDK.
- **Checks:** Ruff, pytest, ESLint, Vite build, Husky, GitHub Actions.
- **Planned:** MongoDB, an ECD knowledge collection, a generative model integration, speech processing, and a QLoRA fine-tuning/evaluation pipeline.

## Repository layout

```text
backend/
  api/v1/endpoints/   Health and authenticated-user endpoints
  api/v1/router.py    API route registration
  core/              Configuration, Firebase initialization, authentication
  schemas/           API response models
  services/          Placeholder package for application services
  main.py            FastAPI application and lifecycle
frontend/
  src/components/    Login, registration, and Google sign-in forms
  src/context/       Authentication state
  src/hooks/         Authentication hook
  src/pages/         Authentication and account-setup screens
  src/services/      Firebase operations and backend API calls
scripts/             Repository checks and Firebase TOTP administration
tests/               Backend health and missing-token tests
.github/workflows/   CI checks
```

The local `notebooks/` directory is currently empty; training notebooks and datasets have not been added. See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for the detailed file guide.

## Local setup

### 1. Prerequisites

- Python **3.12** (the CI version; local checks also pass on Python 3.13).
- Node.js **22.13+ within the 22.x release line**, or Node.js 24+, with npm. CI currently uses Node 20, whose installed version must be at least 20.19 for the frontend tooling.
- A Firebase project with Authentication upgraded to **Firebase Authentication with Identity Platform** for TOTP MFA.
- A Firebase web app and a service-account JSON key for the same project.
- An authenticator app for exercising the complete login flow.

No GPU or MongoDB instance is needed to run the current authentication prototype.

### 2. Install dependencies

Run from the repository root. The following commands use Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci --include=optional
npm --prefix frontend ci --include=optional
```

The explicit optional-dependency flag includes platform-specific frontend tooling despite the root `.npmrc` setting. Root installation also configures the Husky Git hooks.

On macOS/Linux, use `venv/bin/python` in place of `.\venv\Scripts\python.exe`.

### 3. Configure environment files

For a fresh checkout, copy the templates (preserve existing local configuration):

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

Set the backend values in `.env`:

| Variable | Purpose |
| --- | --- |
| `FIREBASE_PROJECT_ID` | Firebase project shared with the frontend |
| `FIREBASE_ADMIN_KEY_PATH` | Service-account JSON path, e.g. `.secrets/firebase-admin.json`; relative paths resolve from the repository root |
| `HOST`, `PORT` | Loaded by the settings class; the current Uvicorn command does not automatically apply them |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | Future AI integration placeholders; not required for current features |

Create `.secrets/` if needed and place the service-account file at the configured path. The backend requires a matching project ID and key, and currently rejects `FIREBASE_AUTH_EMULATOR_HOST`.

Set these values in `frontend/.env.local` using the Firebase web app configuration:

```dotenv
VITE_FIREBASE_API_KEY=your_firebase_web_api_key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project
VITE_FIREBASE_APP_ID=your_firebase_web_app_id
```

`VITE_*` values are included in browser code. Service-account credentials and AI provider secrets belong on the backend. Local environment files and `.secrets/` are Git-ignored.

### 4. Configure Firebase Authentication

In the Firebase console:

1. Enable **Email/Password** and **Google** sign-in providers.
2. Add `localhost` to Authentication's authorized domains if absent.
3. Ensure Identity Platform is enabled and configure TOTP MFA.

The repository includes scripts for inspecting and enabling TOTP. Run them from the root after filling `.env`:

```powershell
# Inspect the current cloud project configuration.
node --env-file=.env scripts/check-firebase-auth.mjs

# Enable TOTP in that Firebase project if it is not configured.
node --env-file=.env scripts/enable-firebase-totp.mjs
```

The second script changes the project's MFA configuration. These scripts are administrative tools, not part of normal application startup.

### 5. Start the application

Backend, in one terminal:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in another terminal:

```powershell
npm run dev:frontend
```

Open:

- Application: <http://localhost:5173>
- Backend API docs: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/health/live>

Vite uses a fixed port of 5173 and proxies to backend port 8000. If you change the backend port, update `frontend/vite.config.js` too. The proxy is a development-server feature; serving `frontend/dist` separately requires equivalent API routing in the deployment configuration.

### 6. Exercise the account flow

1. Register or sign in with Google.
2. Verify the email if needed and refresh its status in the account screen.
3. Enroll an authenticator by scanning the QR code and confirming a six-digit code.
4. Log out, then log in and complete the authenticator challenge.
5. Click **Check backend access** to verify that FastAPI accepts the session.

Enrolling an authenticator is distinct from completing an MFA login. The backend requires the current token to identify a TOTP-authenticated session.

## Current API

| Method | Direct backend path | Access | Response |
| --- | --- | --- | --- |
| GET | `/health/live` | Public | `{"status":"ok"}` |
| GET | `/me` | Verified email and TOTP-authenticated Firebase token | `{"uid":"..."}` |

Both endpoints are also mounted under `/api/v1`, giving `/api/v1/health/live` and `/api/v1/me`. Through the Vite development proxy, the current frontend uses `/api/me` for the root `/me` endpoint.

Protected requests require `Authorization: Bearer <Firebase ID token>`. Authentication can return 401 for missing/invalid login, 403 for unmet verification/MFA requirements or unsupported tenants, and 503 if verification services are unavailable.

## Checks and development commands

```powershell
npm run check
```

This runs Python lint, backend tests, frontend lint, and a production frontend build. The runner finds `.venv` or `venv` automatically, then falls back to `python` on PATH.

| Command | Action |
| --- | --- |
| `npm run dev:backend` | Start Uvicorn with reload; requires the Python environment activated/on PATH |
| `npm run dev:frontend` | Start Vite |
| `npm run test:backend` | Run pytest; requires the Python environment activated/on PATH |
| `npm run test:frontend` | Run ESLint only; no frontend behavioural test suite is configured |
| `npm run lint:backend` | Run Ruff; requires the Python environment activated/on PATH |
| `npm run lint:frontend` | Run ESLint |
| `npm run build:frontend` | Build to `frontend/dist/` |

The pre-push hook runs `npm run check`. GitHub Actions runs backend lint/tests and frontend lint/build on pushes and pull requests targeting `main`.

**Verification snapshot (28 September 2026):** all configured checks pass, including four backend tests. Tests mock Firebase initialization and cover health responses and missing-token rejection for both route prefixes. They do not establish that live email delivery, Google sign-in, or TOTP works in a configured cloud project. Broader authentication and UI integration coverage remains to be added.

## Next milestone: child profiles and text coaching

### 1. Implement child profiles and persistence

- Add MongoDB configuration and a shared database lifecycle.
- Define a child profile with an owner Firebase UID, display name, birth date, and timestamps; calculate age from birth date.
- Add authenticated create, list, read, update, and delete endpoints. Derive ownership from the verified token.
- Add a child-profile dashboard after account setup, including profile creation and selection.
- Test persistence, invalid dates, and cross-account isolation. Expand authentication tests for valid tokens, unverified email, missing TOTP, and rejected/revoked tokens.

**Done when:** a verified caregiver can create and select a profile, see it after reloading, and access only their own profiles.

### 2. Prepare the ECD pilot dataset alongside application work

Start with approximately **200 reviewed coaching examples** to refine the format and coverage. This is a pilot target, not a guaranteed training requirement.

Useful starting sources:

- [WHO/UNICEF Care for Child Development](https://www.unicef.org/documents/care-child-development): counselling cards and participant manual.
- [CDC developmental milestones](https://www.cdc.gov/act-early/milestones/): age references and caregiver activities.
- [Kenya Ministry of Health Mother & Child Health Handbook](https://health.go.ke/sites/default/files/2023-05/Mother%20Child%20Health%20Handbook%20MOH-FOR%20PRINT.pdf): locally relevant developmental guidance.
- [CHILDES](https://talkbank.org/childes/access/index.html): supporting interaction examples, subject to corpus access and reuse terms. Transcripts are observations, not expert coaching answers.

Keep source passages for retrieval separate from coaching question/answer examples. Record age, routine, developmental domain, source/version/section, review status, and a scenario-group ID. Preserve provenance and applicable reuse terms.

Create grouped training/validation/test splits (approximately 80/10/10), keeping families, conversations, and related scenario variants together. Split before augmenting training examples. Prepare independent evaluation cases and a reviewer rubric for developmental appropriateness, source support, relevance, clarity, and usefulness.

### 3. Build a text-first coaching baseline

- Add a routine selector and text question form for the selected child.
- Define a coaching request/response schema and a backend model service.
- Integrate a pretrained instruction model and record its baseline performance.
- Add retrieval from the curated ECD knowledge collection and display source references.
- Persist conversations and caregiver feedback in MongoDB.

**Done when:** a caregiver can ask a text question for a selected child/routine, receive a model-generated response with supporting references, and revisit the exchange.

### 4. Fine-tune and evaluate

Expand the reviewed dataset as needed, then fine-tune a selected instruction model using QLoRA. Compare base, base + RAG, fine-tuned, and fine-tuned + RAG configurations. Use validation data for tuning and freeze choices before held-out testing. Keep test questions and reference answers out of the retrieval index.

Prioritize expert-reviewed coaching quality and grounding; use BERTScore/ROUGE only as supplementary metrics. Record model/data versions, hyperparameters, hardware, and results. Evaluating response quality does not establish a long-term improvement in child development.

### 5. Add voice and end-to-end evaluation

Integrate pretrained speech-to-text and text-to-speech services. Evaluate adult caregiver speech under the intended indoor conditions, including target accents, age/negation transcription errors, intelligibility, and end-to-end latency. Keep speakers separate across splits if adapting the speech model.

## Project scope

The intended assistant supports everyday developmental interaction for children aged 0–24 months. Medical diagnosis and treatment recommendations are outside the proposal's scope. The initial research deliverable is a functioning coaching prototype with a reproducible dataset and evaluation process.
