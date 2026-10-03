# Project File Structure & Architecture Guide

This document explains the complete file structure of the **Parenting Voice Assistant** project: what each folder and file does, what code is inside it, how the parts connect to each other, and how data flows through the application.

---

## 1. High-Level Architecture

The system has three main parts:

```text
React Frontend (Vite)
  │
  ├── 1. Talks directly to Firebase Auth (sign in, sign up, MFA verification)
  │
  └── 2. Sends requests with a Firebase ID token to FastAPI (/api/me, etc.)
            │
            ▼
      FastAPI Backend
        │
        ├── Verifies ID token signature with Firebase Admin SDK
        ├── Enforces email verification & TOTP MFA rules
        └── Returns protected user data
```

---

## 2. Directory Map

```text
parenting-voice-assistant/
│
├── .github/
│   └── workflows/
│       └── ci.yml               # automated checks on github actions (lint, test, build)
│
├── .husky/
│   ├── _/                       # husky internal helper files (auto-generated)
│   ├── .gitattributes           # ensures hook scripts keep correct line endings
│   └── pre-push                 # runs 'npm run check' locally before every git push
│
├── .secrets/
│   └── firebase-admin.json      # private service account key (git-ignored, never committed)
│
├── backend/                     # python backend (fastapi)
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py      # /me endpoint (checks token, returns user id)
│   │       │   └── health.py    # /health/live endpoint (server liveness check)
│   │       └── router.py        # groups endpoints into a single api router
│   ├── core/
│   │   ├── config.py            # loads settings and environment variables
│   │   ├── firebase.py          # initializes firebase admin sdk on startup
│   │   └── security.py          # dependency that checks bearer token, email & totp
│   ├── schemas/
│   │   └── auth.py              # pydantic data models for api request/response bodies
│   └── main.py                  # entry point of fastapi: startup, shutdown, routes
│
├── frontend/                    # react client (vite)
│   ├── public/                  # static assets (icons, favicon)
│   ├── src/
│   │   ├── components/
│   │   │   ├── GoogleSignInButton.jsx # button for google popup sign-in
│   │   │   ├── LoginForm.jsx          # email/password login and password reset form
│   │   │   └── SignUpForm.jsx         # email/password account creation form
│   │   ├── context/
│   │   │   ├── AuthContext.js         # react context object for auth state
│   │   │   └── AuthProvider.jsx       # provider listening to firebase auth changes
│   │   ├── hooks/
│   │   │   └── useAuth.js             # custom hook for easy access to auth state
│   │   ├── pages/
│   │   │   ├── AccountPage.jsx        # email verification, qr code, totp setup & logout
│   │   │   └── AuthPage.jsx           # switches between login, signup, and totp challenge
│   │   ├── services/
│   │   │   ├── api.js                 # calls python backend (/api/me) with bearer token
│   │   │   ├── auth.js                # all browser firebase operations (login, totp, etc.)
│   │   │   └── firebase.js            # initializes client-side firebase sdk
│   │   ├── App.jsx                    # main component switching between auth and account
│   │   ├── index.css                  # global base css
│   │   └── main.jsx                   # react root mount with StrictMode
│   ├── .env.example             # template for frontend environment variables
│   ├── .env.local               # local frontend config with firebase web keys (ignored)
│   ├── eslint.config.js         # eslint rules for react
│   ├── package.json             # frontend dependencies (firebase, react, qrcode)
│   └── vite.config.js           # vite dev server config & proxy forwarding /api to fastapi
│
├── scripts/                     # developer tooling and verification scripts
│   ├── check.mjs                # unified runner: python lint, tests, frontend lint, build
│   ├── check-firebase-auth.mjs  # read-only tool to inspect firebase mfa settings
│   └── enable-firebase-totp.mjs # one-time script to enable totp in firebase project
│
├── tests/                       # backend tests (pytest)
│   ├── conftest.py              # test fixtures: mocks firebase admin and creates test client
│   ├── test_auth.py             # tests that /me rejects unauthenticated requests (401)
│   └── test_health.py           # tests that /health/live responds with 200 ok
│
├── .env.example                 # template for backend environment variables
├── .gitignore                   # files and folders excluded from git tracking
├── .npmrc                       # npm settings (omit optional packages)
├── package.json                 # root repository tooling (husky, check script)
├── pyproject.toml               # ruff linter and pytest configuration
├── requirements.txt             # backend python production dependencies
└── requirements-dev.txt         # development dependencies (includes ruff)
```

---

## 3. Detailed File Breakdown

### Root Configuration & Tooling

#### `.env.example`
- **What it does:** Template showing which environment variables the backend expects.
- **Variables inside:** `FIREBASE_PROJECT_ID`, `FIREBASE_ADMIN_KEY_PATH`, `HOST`, `PORT`, `GEMINI_API_KEY`.
- **Connections:** You copy this to `.env` (which stays secret and git-ignored). `backend/core/config.py` reads these values at runtime.

#### `pyproject.toml`
- **What it does:** Central configuration file for Python developer tools.
- **Sections inside:**
  - `[tool.ruff]`: Ignores folders like `venv`, `node_modules`, `frontend/dist`.
  - `[tool.ruff.lint]`: Selects standard lint rule categories (E, F).
  - `[tool.pytest.ini_options]`: Sets `pythonpath = ["."]` so tests can find `backend` without path errors.
- **Connections:** Used by `ruff check .` and `pytest` both locally and in CI.

#### `package.json` (Root)
- **What it does:** Defines repository-level scripts and tools.
- **Scripts inside:**
  - `npm run check`: Executes `node scripts/check.mjs`.
  - `npm run prepare`: Sets up Husky git hooks.
  - `dev:backend`, `dev:frontend`, `test:backend`, `test:frontend`: Shortcuts to run parts individually.
- **Connections:** Used by developers and Git hooks to run multi-language checks.

#### `.husky/pre-push`
- **What it does:** Git hook script executed automatically whenever you type `git push`.
- **Code inside:** Runs `npm run check`. If any check fails, the push is stopped.
- **Connections:** Triggers `scripts/check.mjs`.

---

### Scripts Folder (`scripts/`)

#### `scripts/check.mjs`
- **What it does:** Single script that runs all project verification checks in order:
  1. Python lint (`python -m ruff check .`)
  2. Python tests (`python -m pytest`)
  3. Frontend lint (`npm --prefix frontend run lint`)
  4. Frontend build (`npm --prefix frontend run build`)
- **Key logic:** Automatically finds the virtual environment Python executable (`venv/Scripts/python.exe` on Windows or `venv/bin/python` on Linux). Exits immediately with an error code if any step fails.
- **Connections:** Called by `.husky/pre-push` locally and by `npm run check`.

#### `scripts/check-firebase-auth.mjs`
- **What it does:** Read-only inspection script.
- **Key logic:** Authenticates to Firebase using the Admin SDK private key and queries `projectConfigManager().getProjectConfig()` to check whether TOTP MFA is currently enabled.
- **Connections:** Safe to run anytime to verify project configuration without modifying cloud settings.

#### `scripts/enable-firebase-totp.mjs`
- **What it does:** Administrative setup script.
- **Key logic:** Uses the Firebase Admin SDK to update the project configuration, activating the TOTP second-factor provider with an adjacent interval of 1 (clock drift allowance).
- **Connections:** Run once to turn on TOTP support in Firebase Authentication with Identity Platform.

---

### Backend (`backend/`)

#### `backend/main.py`
- **What it does:** The main FastAPI application factory and entry point.
- **Code inside:**
  - `lifespan`: Startup/shutdown manager. Calls `initialize_firebase()` on startup and `firebase_admin.delete_app()` on shutdown.
  - `app`: FastAPI application instance.
  - Mounts routes from `backend.api.v1.router.api_router` both at root (`/health/live`, `/me`) and with version prefix (`/api/v1/health/live`, `/api/v1/me`).
- **Connections:** Run by Uvicorn server (`uvicorn backend.main:app`).

#### `backend/core/config.py`
- **What it does:** Reads and validates configuration settings from `.env`.
- **Key logic:** Defines `Settings` class with properties for `PROJECT_NAME`, `FIREBASE_PROJECT_ID`, and a helper `firebase_admin_key_path` that safely resolves relative or absolute key file paths.
- **Connections:** Imported by `backend/core/firebase.py` and `backend/main.py`.

#### `backend/core/firebase.py`
- **What it does:** Creates the shared Firebase Admin SDK application instance.
- **Key logic:** Loads `credentials.Certificate(key_path)`, verifies the credential matches the project id, prevents accidental emulator connections in production, and calls `firebase_admin.initialize_app()`.
- **Connections:** Called by the `lifespan` function in `backend/main.py`.

#### `backend/core/security.py`
- **What it does:** The gatekeeper for private backend endpoints.
- **Key function: `require_authenticated_user`:**
  1. Reads `Authorization: Bearer <token>` from the HTTP request.
  2. Calls `auth.verify_id_token(token, check_revoked=True)` via Firebase Admin.
  3. Checks that `email_verified` is `True` (rejects with HTTP 403 if unverified).
  4. Checks that `firebase.sign_in_second_factor == "totp"` (rejects with HTTP 403 if MFA was skipped).
  5. Returns a dictionary containing the verified `uid`.
- **Connections:** Used as a dependency (`Depends(require_authenticated_user)`) on private routes like `GET /me`.

#### `backend/api/v1/endpoints/auth.py`
- **What it does:** Endpoint handler for `/me`.
- **Code inside:** Calls `require_authenticated_user`, sets `Cache-Control: no-store` header, and returns a `UserResponse(uid=...)`.
- **Connections:** Included into `backend/api/v1/router.py`.

#### `backend/api/v1/endpoints/health.py`
- **What it does:** Public liveness check endpoint `/health/live`.
- **Code inside:** Returns `{"status": "ok"}`.
- **Connections:** Included into `backend/api/v1/router.py`.

#### `backend/schemas/auth.py`
- **What it does:** Defines the JSON shape for responses using Pydantic models.
- **Models inside:**
  - `HealthResponse`: `status: str`
  - `UserResponse`: `uid: str`
- **Connections:** Used by endpoints in `backend/api/v1/endpoints/` for automatic data validation and documentation.

#### Core module imports
- Backend modules import configuration, Firebase initialization, and authentication directly from `backend.core.*`.
- The former root-level compatibility bridge files have been removed from the working tree.

---

### Frontend (`frontend/src/`)

#### `frontend/src/services/firebase.js`
- **What it does:** Initializes client-side Firebase in the browser.
- **Code inside:** Reads `import.meta.env.VITE_FIREBASE_*` variables and exports the shared `auth` object (`getAuth(app)`).
- **Connections:** Imported by `services/auth.js`, `services/api.js`, and `context/AuthProvider.jsx`.

#### `frontend/src/services/auth.js`
- **What it does:** Collection of all browser Firebase Authentication operations.
- **Functions inside:**
  - `signInWithGoogle()`: Opens Google popup; returns `{ next: "signed-in", user }` or `{ next: "mfa-required", resolver }`.
  - `signInWithEmail(email, password)`: Logs in existing user; handles both normal login and MFA challenge.
  - `signUpWithEmail(email, password)`: Creates user account and immediately attempts to send verification email.
  - `resendVerificationEmail()`: Reloads user, checks if already verified, and requests another email if not.
  - `logOut()`: Signs out of Firebase.
  - `requestPasswordReset(email)`: Sends password reset email.
  - `beginTotpEnrollment()`: Verifies email is verified, then generates a temporary TOTP setup secret.
  - `confirmTotpEnrollment(pending, code)`: Enrolls the TOTP factor using the entered 6-digit code.
  - `completeTotpSignIn(resolver, code)`: Resolves a pending MFA login challenge using the entered code.
  - `getAccountSecurityStatus()`: Returns `{ emailVerified, totpEnrolled }`.
- **Connections:** Called by UI components and pages (`AccountPage`, `AuthPage`, `LoginForm`, `SignUpForm`).

#### `frontend/src/services/api.js`
- **What it does:** Client for calling your own Python backend.
- **Function inside: `getCurrentAccount()`:**
  1. Gets current Firebase user.
  2. Calls `user.getIdToken()` to obtain a signed token.
  3. Sends `GET /api/me` with `Authorization: Bearer <token>`.
  4. Returns the backend JSON response or throws an error with the backend's message.
- **Connections:** Called by the "Check backend access" test button on `AccountPage.jsx`.

#### `frontend/src/context/AuthContext.js` & `frontend/src/context/AuthProvider.jsx`
- **What it does:** Global React state management for authentication.
- **Key logic:** `AuthProvider` subscribes to Firebase's `onAuthStateChanged(auth, callback)`. When auth status changes, it updates `user` and sets `checkingAuth: false`. Provides `user`, `checkingAuth`, `signupResult`, `setSignupResult`, and `logout` to the whole component tree.
- **Connections:** Wraps `MainContent` in `App.jsx`.

#### `frontend/src/hooks/useAuth.js`
- **What it does:** Custom helper hook.
- **Code inside:** Calls `useContext(AuthContext)` and provides clean access to authentication data.
- **Connections:** Used inside `App.jsx`.

#### `frontend/src/pages/AuthPage.jsx`
- **What it does:** The signed-out screen.
- **Key logic:**
  - Holds `mode` state (`"login"` or `"signup"`).
  - Holds `mfaResolver` state: if an MFA challenge occurs during Google or email login, it replaces the form with a 6-digit authenticator code entry form.
  - Contains `<GoogleSignInButton />` and toggles between `<LoginForm />` and `<SignUpForm />`.
- **Connections:** Rendered by `App.jsx` when `user` is `null`.

#### `frontend/src/pages/AccountPage.jsx`
- **What it does:** The signed-in screen for account status and MFA setup.
- **Key logic:**
  - Displays user email and verification status.
  - When unverified: provides "Check Verification Status" and "Resend Verification Email" (with 60-second cooldown timer).
  - When verified: provides "Set up authenticator" button.
  - Generates a local QR code via `qrcode` library alongside a manual text setup key.
  - Confirms enrollment using a 6-digit code input.
  - Provides "Log Out" and "Check backend access" buttons.
- **Connections:** Rendered by `App.jsx` when `user` is present.

#### `frontend/src/components/GoogleSignInButton.jsx`
- **What it does:** Self-contained button for Google authentication.
- **Key logic:** Handles popup errors (popup closed by user, popup blocked) and forwards MFA challenges via `onMfaRequired` prop.
- **Connections:** Used inside `AuthPage.jsx`.

#### `frontend/src/components/LoginForm.jsx`
- **What it does:** Form for email and password login.
- **Key logic:** Calls `signInWithEmail`, handles loading state, clears password and forwards challenge on MFA, and includes "Forgot Password?" button.
- **Connections:** Used inside `AuthPage.jsx`.

#### `frontend/src/components/SignUpForm.jsx`
- **What it does:** Form for creating a new account.
- **Key logic:** Displays password requirements, validates inputs, calls `signUpWithEmail`, and notifies parent via `onAccountCreated`.
- **Connections:** Used inside `AuthPage.jsx`.

#### `frontend/src/App.jsx`
- **What it does:** Top-level layout.
- **Key logic:** Uses `useAuth()`. While `checkingAuth` is true, renders "Checking sign-in...". When authenticated, renders `<AccountPage />`. When signed out, renders `<AuthPage />`.
- **Connections:** Rendered into `index.html` via `main.jsx`.

#### `frontend/vite.config.js`
- **What it does:** Vite dev server configuration.
- **Key logic:** Configures development proxy rule: any request to `/api/*` is forwarded to `http://127.0.0.1:8000/*` (with `/api` prefix stripped).
- **Connections:** Allows `frontend/src/services/api.js` to call `/api/me` without CORS issues in local development.

---

### Backend Tests (`tests/`)

#### `tests/conftest.py`
- **What it does:** Shared pytest setup.
- **Key logic:**
  - Adds project root to `sys.path`.
  - Sets dummy environment variables for tests.
  - `mock_firebase_app` fixture: mocks `initialize_firebase` and `delete_app` so tests don't require internet or real private keys.
  - `client` fixture: creates a FastAPI `TestClient(app)`.
- **Connections:** Automatically loaded by pytest when running tests in `tests/`.

#### `tests/test_health.py`
- **What it does:** Verifies that both `/health/live` and `/api/v1/health/live` return HTTP 200 with `{"status": "ok"}`.
- **Connections:** Executed by `pytest`.

#### `tests/test_auth.py`
- **What it does:** Verifies that both `/me` and `/api/v1/me` return HTTP 401 `{"detail": "Login required."}` when called without an Authorization header.
- **Connections:** Executed by `pytest`.

---

### GitHub Actions (`.github/workflows/ci.yml`)

- **What it does:** Runs continuous integration on every `push` and `pull_request` to `main`.
- **Jobs inside:**
  - `backend-checks`: Sets up Python 3.12, installs `requirements-dev.txt`, runs `ruff check .`, runs `pytest` with `PYTHONPATH: .`.
  - `frontend-checks`: Sets up Node 20, runs `npm ci` in `frontend/`, runs `npm run lint`, runs `npm run build`.
- **Connections:** Executes automatically on GitHub's cloud servers.

---

## 4. End-to-End Request Flow Summary

```text
1. USER CLICKS "Check backend access" in React:
   AccountPage.jsx -> handleBackendCheck()
     │
     ▼
2. GET FIREBASE ID TOKEN:
   api.js -> auth.currentUser.getIdToken()
     │
     ▼
3. HTTP REQUEST SENT:
   Browser -> GET /api/me
   Header: Authorization: Bearer <token>
     │
     ▼
4. VITE DEV PROXY:
   vite.config.js forwards /api/me to http://127.0.0.1:8000/me
     │
     ▼
5. FASTAPI ROUTE DISPATCH:
   backend/main.py -> backend/api/v1/endpoints/auth.py -> current_user()
     │
     ▼
6. SECURITY DEPENDENCY EXECUTION:
   backend/core/security.py -> require_authenticated_user()
     ├── verify_id_token() signature checked with Firebase Admin
     ├── check_revoked=True confirms token not revoked
     ├── email_verified == True confirmed
     └── sign_in_second_factor == "totp" confirmed
     │
     ▼
7. SUCCESS RESPONSE:
   FastAPI returns 200 OK with {"uid": "..."}
     │
     ▼
8. UI UPDATE:
   AccountPage displays "Backend accepted your verified MFA login."
```
