# Parenting Voice Assistant

An AI-powered voice and text conversational assistant designed for caregivers and parents of infants (**birth to 24 months**). The system provides concise, practical, and age-appropriate guidance for everyday parenting routines such as feeding, playtime, soothing, bedtime, and bathing.

---

## Table of Contents

- [What the Project is About](#what-the-project-is-about)
- [Key Features](#key-features)
- [How the System Works](#how-the-system-works)
  - [1. The Voice & Text Interaction Pipeline](#1-the-voice--text-interaction-pipeline)
  - [2. The Authentication & Security Flow](#2-the-authentication--security-flow)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Authentication & Account Security](#authentication--account-security)
- [Local Setup & Installation](#local-setup--installation)
  - [Prerequisites](#prerequisites)
  - [1. Clone and Open the Repository](#1-clone-and-open-the-repository)
  - [2. Install Dependencies](#2-install-dependencies)
  - [3. Configure Environment Variables](#3-configure-environment-variables)
  - [4. Configure Firebase Authentication](#4-configure-firebase-authentication)
  - [5. Run the Application](#5-run-the-application)
- [Current Implementation Status & Roadmap](#current-implementation-status--roadmap)

---

## What the Project is About

Caring for an infant under two years old involves countless questions throughout the day:
* *"My 6-month-old is teething and rejecting solid food during feeding—what should I do?"*
* *"What language stimulation games can I play with my 9-month-old during bath time?"*
* *"How can I encourage motor skills while my baby is doing tummy time?"*

Standard search engines and generic chatbots often return long, dense articles that are difficult for a busy caregiver to read while holding a baby. 

**Parenting Voice Assistant** solves this by providing:
1. **Hands-free voice interaction:** Caregivers can speak directly into their microphone and hear spoken answers back through text-to-speech, without needing to type or look at a screen.
2. **Standard text chat:** Users who prefer typing or reading can interact through a familiar chat interface (similar to ChatGPT).
3. **Context-aware answers:** Advice is tailored to the child's specific developmental stage (age in months) and the active daily routine (feeding, diaper change, bedtime, play).
4. **Strong privacy and security:** Caregiver data, child profiles, and personal conversations are protected behind enterprise-grade authentication with email verification and Two-Factor Authentication (MFA).

> **Scope Note:** The application focuses on interactive parenting support and developmental activities. It does not provide medical diagnosis, clinical treatment, image/video analysis, or voice biometric identification.

---

## Key Features

### Available now: English speech-to-text (version 1)

The landing page links to login/signup and, after sign-in, microphone controls.
Record up to **30 seconds**, press **Stop and transcribe**, and review or edit the
returned text. The backend requires a verified email and completed TOTP login.
Transcription uses pretrained **Whisper `tiny.en`**, through faster-whisper on CPU
with INT8. It does not train on recordings or edits and requires no paid speech API.

This version transcribes **after Stop**, not while speaking. Recognition substitutions
were observed on real caregiver questions. Model comparison and accuracy improvements
are deferred to version 2; neither industry-standard accuracy nor live latency has
been established. Audio and transcripts are not deliberately saved by the application.

#### Start speech transcription locally (Windows)

After completing the Firebase setup below, install dependencies from the project root:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd --prefix frontend ci --include=optional
```

Run the backend in one terminal and leave it running:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Wait for **Application startup complete**. Startup loads the model once per server
process; the first load downloads weights to the default Hugging Face cache outside
the repository. Cached model inference is local; Firebase still requires internet.
Use one Uvicorn worker to avoid duplicating model memory.

In another terminal, run:

```powershell
npm.cmd run dev:frontend
```

Open **http://localhost:5173**, sign in and complete email/MFA setup in **My Account**,
then return home. Click **Start recording**, wait for **Recording…**, speak, and stop.
Both servers must stay running. If Vite reports `ECONNREFUSED 127.0.0.1:8000` or a
502/unreadable response, check that the backend has finished starting on port 8000.

Use a current Chrome, Edge, Firefox, or Safari version supporting AudioWorklet and
OfflineAudioContext. Microphone access requires localhost or HTTPS. If permission
is blocked, set Microphone to Allow in the browser's site settings and reload.
Start again replaces the previous transcript. Cancel stops the browser waiting for
transcription; server inference already running may still finish. Retry is manual.
Transcription requests time out after 60 seconds. Edits stay in page memory and are
not submitted to RAG. There are no playback, download, or confirmation requirements.

`STT_MODEL` in the root `.env` selects the model (default `tiny.en`). Restart the
backend after changing it. Larger models require more resources. Model changes do
not require retraining; domain fine-tuning is a separate future experiment.

#### API and deployment

`POST /speech/transcribe` (also `/api/v1/speech/transcribe`) accepts a raw `audio/wav`
body with a Firebase Bearer token: mono, PCM16, 16000 Hz, longer than zero and at most
30 seconds. Body limit: **964096 bytes**, including header. It returns `text`,
`audio_seconds`, and `processing_seconds`. Requests are authenticated and inference
is limited to one at a time per server process; additional inference requests receive
429. Audio validation, unsupported format, and service failures return explicit errors.

The frontend calls `/api/speech/transcribe`. Vite removes `/api` and forwards to
`http://127.0.0.1:8000` during development. A deployed frontend needs an HTTPS,
same-origin reverse proxy implementing the same mapping (or a deliberately updated
API client); the development proxy is not part of the built static files.

#### Verification and limitations

Run `npm.cmd run check` for backend tests, frontend lint, audio utility tests, React
interaction tests, and the production build. Automated browser-resource tests use
simulated devices; they do not replace manual microphone checks.

User-reported checks passed for speech submission, silence, transcript editing,
automatic stop, restart, logout cleanup, and request cancellation. On one reported
recording, 4.18 seconds of audio took 1.33 seconds of server processing and roughly
3 seconds from Stop to displayed text. The sentence "my baby is crying what should
I do what are the suggestions" was misrecognized as "I may be scrying what you like,
what I was suggestions." These observations establish connectivity and illustrate
a known accuracy limitation, not a benchmark. Browser/OS details and timing method
should accompany any future quantitative evaluation.

The final responsive landing layout still needs a real-browser visual check on
narrow and wide screens. Full device/browser coverage and live transcription remain
future work.

* **Multi-Modal Input (Voice & Text):** Speak via microphone or type questions in text.
* **Dual Output (Audio & Text):** Responses are displayed on-screen and converted into natural speech output.
* **Child Profile Context:** Answers adapt to the child's age in months and current developmental milestones.
* **Routine-Based Coaching:** Focus prompts around real caregiving moments (e.g., bath, mealtime, play, bedtime).
* **Multi-Factor Authentication (2FA/MFA):** Supports email/password, Google OAuth, mandatory email verification, and time-based one-time password (TOTP) authenticator apps (Google Authenticator, Authy, etc.).
* **Verified Backend API:** Backend endpoints strictly validate Firebase ID tokens, verifying token signatures, email confirmation, and second-factor status before returning data.
* **Conversation History & Feedback:** Caregivers can review past conversations and submit feedback ratings to improve future interactions.

---

## How the System Works

### 1. The Voice & Text Interaction Pipeline

This is how a caregiver interacts with the voice assistant from start to finish:

```text
       Caregiver
       (Speaks into Mic OR Types Question)
                      │
                      ▼
            React Web Frontend
       ┌──────────────────────────────┐
       │ • Records voice audio (WAV)  │
       │ • Or collects typed text     │
       └──────────────┬───────────────┘
                      │
                      │ HTTP POST (with Firebase Auth Token)
                      ▼
               FastAPI Backend
       ┌──────────────────────────────┐
       │ 1. Verifies user identity    │
       │ 2. Speech-to-Text (STT)      │
       │    Converts voice to text    │
       │ 3. Context Enrichment        │
       │    Loads child age & routine │
       │ 4. LLM Reasoning Engine      │
       │    (Planned)                 │
       │    Generates tailored advice │
       │ 5. Text-to-Speech (TTS)      │
       │    Converts answer to audio  │
       └──────────────┬───────────────┘
                      │
                      │ Returns JSON: Text Response + Audio Stream/File
                      ▼
            React Web Frontend
       ┌──────────────────────────────┐
       │ • Displays chat message      │
       │ • Plays spoken audio answer  │
       └──────────────────────────────┘
```

#### Step-by-Step Breakdown:

1. **Input Capture:** 
   * If voice: The browser records the caregiver's speech via the Web Audio / MediaRecorder API.
   * If text: The caregiver types the query into the chat input.
2. **Transport & Security:** The frontend sends the request to the FastAPI backend, including a verified Firebase ID token in the `Authorization: Bearer <token>` header.
3. **Speech-to-Text (STT, planned):** The backend will transcribe microphone audio using a locally served model fine-tuned on domain-specific audio/transcript pairs. Training and inference are not implemented yet.
4. **Context Injection:** The backend attaches the child's profile (e.g., age: 8 months) and current routine (e.g., playtime) to the prompt.
5. **AI Generation (LLM, planned):** The enriched prompt will be used to generate concise, friendly, and practical guidance. The coaching model is still to be selected.
6. **Text-to-Speech (TTS, planned):** A future TTS engine will synthesize the generated answer. No TTS runtime is currently installed or connected.
7. **Playback & Display:** The frontend receives the response, appends it to the chat conversation history, and plays the audio answer aloud.

---

### 2. The Authentication & Security Flow

Security is built into both the frontend and backend to protect sensitive family data:

```text
React Frontend (Vite)                FastAPI Backend (Python)              Firebase Auth / Identity Platform
       │                                        │                                       │
       │─── 1. Sign In (Email/Pass or Google) ─>│                                       │
       │    (Handled directly via SDK) ─────────┼──────────────────────────────────────>│
       │                                        │                                       │
       │<── 2. Prompts 2FA / TOTP Challenge ────┼───────────────────────────────────────│
       │                                        │                                       │
       │─── 3. Submits 6-digit Authenticator ──>│                                       │
       │       Code to resolve MFA ─────────────┼──────────────────────────────────────>│
       │                                        │                                       │
       │<── 4. Issues signed Firebase ID Token ─┼───────────────────────────────────────│
       │                                        │                                       │
       │─── 5. Calls Protected API (/me) ──────>│                                       │
       │       Header: Authorization: Bearer    │                                       │
       │                                        │─── 6. verify_id_token(check_revoked) ─>│
       │                                        │<── 7. Returns token claims & UID ─────│
       │                                        │                                       │
       │                                        │─── 8. Enforces Rules:                 │
       │                                        │       • Token valid & not revoked     │
       │                                        │       • Email is verified (True)      │
       │                                        │       • Second factor == "totp"       │
       │                                        │                                       │
       │<── 9. Returns 200 OK with User UID ────│                                       │
```

---

## System Architecture

The application is structured as a decoupled client-server architecture:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          CLIENT (Frontend)                             │
│                                                                        │
│   React 19 (SPA) + Vite 8                                              │
│   ├── Auth UI: Login, Sign-up, Google Sign-in, Password Reset          │
│   ├── 2FA/MFA: QR Code Generator, TOTP Verification Form               │
│   ├── Chat UI: Conversation Feed, Voice Recording Button               │
│   └── Audio Player: Plays synthesized spoken responses                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         HTTP / REST API (JSON)
                      + WebSocket / Audio Stream
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                          SERVER (Backend)                              │
│                                                                        │
│   FastAPI (Python 3.12 / 3.13)                                         │
│   ├── Security Layer: Firebase Admin SDK, Token & 2FA Verification     │
│   ├── API Endpoints: Health check, User Identity (/me), Conversations  │
│   ├── Voice Pipeline: Speech-to-Text (STT); TTS planned               │
│   ├── AI Coaching Service: Prompt formatting, LLM API calls            │
│   └── Data Persistence: Conversations, feedback, and child profiles    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               ▼                                         ▼
   Planned Model Services                   Firebase Identity Platform
   • Domain-fine-tuned speech model          • User accounts & passwords
   • Coaching model (to be selected)         • Google OAuth provider
   • Locally served speech recognition      • TOTP second-factor engine
```

---

## Technology Stack

### Frontend
* **Core:** React 19, JavaScript (ES Modules), HTML5 Audio API
* **Build Tool:** Vite 8 (Hot Module Replacement, fast build pipeline)
* **Authentication:** Firebase Web SDK v12 (Client-side sign-in, MFA resolution)
* **Utilities:** `qrcode` (renders local TOTP provisioning QR codes without third-party services)
* **Styling:** CSS3 (responsive flexbox/grid, custom design tokens, dark mode support)

### Backend
* **Web Framework:** FastAPI (high-performance asynchronous Python API framework)
* **Server:** Uvicorn (ASGI server with auto-reload for local development)
* **Data Validation:** Pydantic v2 (strict type checking and response schema serialization)
* **Authentication:** Firebase Admin SDK Python (cryptographic verification of ID tokens, revocation checking)
* **Speech Processing:** `faster-whisper` and PyAV for CPU transcription of raw WAV request bodies; no multipart upload or TTS dependency is currently needed.
* **Speech-to-Text Training (planned):** Fine-tune a pretrained speech model on domain-specific audio/transcript pairs and compare it with the current pretrained baseline.

### Developer Tooling & Quality Assurance
* **Testing:** `pytest`, `pytest-asyncio`, `httpx` (FastAPI TestClient integration tests)
* **Python Linting:** Ruff (ultra-fast Python linter and formatter)
* **Frontend Linting:** ESLint with React Hooks and React Refresh plugins
* **Git Hooks:** Husky (runs automated lint and test checks before every `git push`)
* **CI/CD:** GitHub Actions (runs automated backend and frontend validation on push and pull requests)

---

## Repository Structure

```text
parenting-voice-assistant/
│
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI pipeline (lint, test, build)
│
├── .husky/
│   └── pre-push                 # Git hook: runs 'npm run check' before pushing code
│
├── .secrets/
│   └── firebase-admin.json      # Firebase Admin service account key (git-ignored)
│
├── backend/                     # FastAPI backend application
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py      # /me endpoint (checks token, returns user UID)
│   │       │   └── health.py    # /health/live liveness check
│   │       └── router.py        # Central API router combining endpoints
│   ├── core/
│   │   ├── config.py            # Environment configuration loader (Pydantic Settings)
│   │   ├── firebase.py          # Firebase Admin SDK initialization and lifespan
│   │   └── security.py          # Auth gatekeeper: validates Bearer token, email, and TOTP
│   ├── schemas/
│   │   └── auth.py              # Pydantic response models (UserResponse, HealthResponse)
│   ├── services/                # Voice, AI, and coaching service logic
│   ├── database.py              # Database connection and schema setup
│   └── main.py                  # FastAPI entry point, lifespan manager, and CORS/router mounting
│
├── frontend/                    # React single-page application
│   ├── public/                  # Favicons and static web assets
│   ├── src/
│   │   ├── components/
│   │   │   ├── GoogleSignInButton.jsx # Google OAuth popup login button
│   │   │   ├── LoginForm.jsx          # Email/password form + forgot password trigger
│   │   │   └── SignUpForm.jsx         # New user registration form with validation rules
│   │   ├── context/
│   │   │   ├── AuthContext.js         # React context for global auth state
│   │   │   └── AuthProvider.jsx       # Context provider tracking Firebase auth changes
│   │   ├── hooks/
│   │   │   └── useAuth.js             # Custom React hook to consume AuthContext
│   │   ├── pages/
│   │   │   ├── AccountPage.jsx        # Email verification status, TOTP enrollment, logout
│   │   │   └── AuthPage.jsx           # Handles login, signup, and TOTP challenge views
│   │   ├── services/
│   │   │   ├── api.js                 # API client for calling FastAPI (/api/me)
│   │   │   ├── auth.js                # Firebase browser SDK wrapper (sign in, sign up, MFA)
│   │   │   └── firebase.js            # Firebase Web SDK initialization
│   │   ├── App.jsx                    # Root view switcher (AuthPage vs AccountPage)
│   │   ├── index.css                  # Global styling and typography
│   │   └── main.jsx                   # React DOM root mounting
│   ├── .env.example             # Frontend environment variable template
│   ├── eslint.config.js         # ESLint configuration
│   ├── package.json             # Frontend dependencies (React, Firebase, Vite)
│   └── vite.config.js           # Vite development server and API proxy configuration
│
├── scripts/                     # Developer utility and administration scripts
│   ├── check.mjs                # Unified local check script (lint + test + build)
│   ├── check-firebase-auth.mjs  # Inspects cloud TOTP MFA configuration (read-only)
│   └── enable-firebase-totp.mjs # Enables TOTP MFA in Firebase project via Admin SDK
│
├── tests/                       # Backend test suite
│   ├── conftest.py              # Pytest fixtures and mocked Firebase lifecycle
│   ├── test_auth.py             # Tests 401 Unauthorized behavior on protected endpoints
│   └── test_health.py           # Tests 200 OK on health endpoints
│
├── .env.example                 # Backend environment variable template
├── .gitignore                   # Git exclusion rules
├── package.json                 # Root scripts and Husky developer dependencies
├── pyproject.toml               # Python tool configurations (Ruff, Pytest)
├── requirements.txt             # Python runtime dependencies
└── requirements-dev.txt         # Python development dependencies (includes Ruff)
```

---

## Authentication & Account Security

The application enforces a multi-tier security model:

### 1. User Registration & Email Verification
* Caregivers can register using their email address and a password (minimum 8 characters with mixed case, numbers, and symbols).
* Upon sign-up, Firebase triggers an account verification email containing a secure, signed action link.
* Unverified accounts are restricted from accessing protected coaching features.

### 2. Sign-In Options
* **Email & Password:** Standard credential login with immediate MFA challenge resolution if enrolled.
* **Google OAuth:** Caregivers can authenticate via Google popup sign-in, reducing password friction while still respecting required 2FA policies.

### 3. Two-Factor Authentication (TOTP MFA)
* Users can enroll an authenticator app (such as Google Authenticator, Microsoft Authenticator, or 1Password).
* The setup secret is generated via Firebase Identity Platform and converted into a QR code locally in the browser using the `qrcode` library (ensuring setup keys are never sent to external QR generation APIs).
* Enrollment is confirmed only after the user enters a valid 6-digit code.
* On future logins, entering email/password prompts an MFA challenge requiring the current 6-digit TOTP code before any session is granted.

### 4. Backend Protection Layer
* When calling the backend, the client requests a signed Firebase ID token.
* The backend (`backend/core/security.py`) verifies the token using the Firebase Admin SDK:
  * Verifies the cryptographic signature against Google's public certificates.
  * Ensures the token is not expired and has not been revoked (`check_revoked=True`).
  * Confirms that `email_verified == True`.
  * Confirms that the login session was authenticated with TOTP (`sign_in_second_factor == "totp"`).
* If any condition fails, the request is rejected with `401 Unauthorized` or `403 Forbidden`.

---

## Local Setup & Installation

### Prerequisites

* **Python:** Version 3.12 or 3.13 installed.
* **Node.js:** Version 20.x, 22.x, or 24.x LTS installed (along with `npm`).
* **Firebase Project:** A Google Firebase project with:
  * **Email/Password** and **Google** enabled in Authentication.
  * **Firebase Authentication with Identity Platform** enabled (required for TOTP MFA).
  * A generated **Service Account Private Key** (JSON file).

---

### 1. Clone and Open the Repository

```powershell
git clone https://github.com/Vinit-Rabadiya/parenting-voice-assistant.git
cd parenting-voice-assistant
```

---

### 2. Install Dependencies

Install backend and frontend dependencies from the project root:

```powershell
# Create and activate Python virtual environment
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# Install root developer tools (Husky git hooks)
npm.cmd ci --include=optional

# Install frontend dependencies
npm.cmd --prefix frontend ci --include=optional
```

*(On macOS/Linux, replace `.\venv\Scripts\python.exe` with `venv/bin/python` and `npm.cmd` with `npm`.)*

---

### 3. Configure Environment Variables

#### A. Backend Configuration (`.env`)
Copy the backend example file:
```powershell
Copy-Item .env.example .env
```

Open `.env` and configure:
```dotenv
HOST=127.0.0.1
PORT=8000

# Firebase Admin Configuration
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_ADMIN_KEY_PATH=.secrets/firebase-admin.json
```

Place your Firebase Admin service account JSON file inside the `.secrets/` directory as `firebase-admin.json` (this directory is excluded from Git).

#### B. Frontend Configuration (`frontend/.env.local`)
Copy the frontend example file:
```powershell
Copy-Item frontend/.env.example frontend/.env.local
```

Open `frontend/.env.local` and add your Firebase Web App credentials:
```dotenv
VITE_FIREBASE_API_KEY=AIzaSy...
VITE_FIREBASE_AUTH_DOMAIN=your-project-id.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_APP_ID=1:1234567890:web:...
```

---

### 4. Configure Firebase Authentication

1. In the [Firebase Console](https://console.firebase.google.com/):
   * Navigate to **Authentication → Sign-in method**.
   * Enable **Email/Password** and **Google**.
   * Under **Settings → Authorized domains**, ensure `localhost` is present.
2. Enable TOTP MFA using the included setup script:
   ```powershell
   node --env-file=.env scripts/enable-firebase-totp.mjs
   ```
   *(To check TOTP status without modifying settings, run `node --env-file=.env scripts/check-firebase-auth.mjs`)*.

---

### 5. Run the Application

#### Start the FastAPI Backend:
In terminal 1:
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
* Interactive API Documentation (Swagger UI): **http://127.0.0.1:8000/docs**
* Health Endpoint: **http://127.0.0.1:8000/health/live**

#### Start the React Frontend:
In terminal 2:
```powershell
npm.cmd run dev:frontend
```
* Open the Web App: **http://localhost:5173**

---

### Running Automated Checks

To run all project checks (Python linting, backend tests, frontend linting, audio and React tests, and production build) in a single command:

```powershell
npm.cmd run check
```

`npm.cmd run test:frontend` runs both audio utility tests and React interaction tests.
`npm.cmd --prefix frontend run check` runs frontend lint, both test suites, and the
production build. GitHub Actions runs these tests as well as lint/build using Node 22.
To target a React test file, use `npm.cmd --prefix frontend run test:ui -- tests/frontend/<file>.test.jsx`.

---

## Current Implementation Status & Roadmap

| Feature / Milestone | Status | Description |
|---|:---:|---|
| **User Sign-up & Login** | Done | Email/password and Google OAuth popup authentication |
| **Email Verification** | Done | Action emails sent on signup; status verification checks |
| **Two-Factor Authentication (2FA)** | Done | TOTP authenticator app enrollment with QR code and login challenge |
| **Backend Authentication Enforcement** | Done | FastAPI verifies ID token, revocation, email confirmation, and TOTP on `/me` |
| **Automated Testing & CI Pipeline** | Done | Pytest test suite, Ruff linter, ESLint, Husky pre-push hooks, and GitHub Actions CI |
| **Child Profiles Management** | Next | Create, update, and select child profiles (birth date, developmental stage) |
| **Voice Input Pipeline** | Implemented (v1) | Authenticated browser recording, pretrained local Whisper transcription after Stop, and editable text; accuracy limitations documented |
| **Live Transcription** | Planned | Periodic audio processing and provisional text updates while speaking |
| **Domain-Specific STT Training** | Planned | Prepare paired parenting-domain audio and transcripts, fine-tune a pretrained model, and evaluate transcription accuracy on held-out speakers |
| **AI Coaching Engine** | Planned | Model selection and domain-specific coaching implementation |
| **Text-to-Speech Output** | Planned | Select and integrate an engine to speak generated answers |
| **Conversation History & Feedback** | Planned | Private history retrieval and caregiver feedback logging |
