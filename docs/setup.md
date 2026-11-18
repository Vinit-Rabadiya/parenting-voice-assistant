# Local setup and service operation

[Documentation home](../README.md#documentation). Commands run from the repository root.

Commands below use Windows PowerShell from the repository root. For macOS/Linux,
use `venv/bin/python` in place of `.\venv\Scripts\python.exe` and `npm` in
place of `npm.cmd`.

## Prerequisites

- Python 3.12 or 3.13. Local verification used 3.13; backend CI uses 3.12.
- Node.js 22 and npm, matching frontend CI.
- A Firebase project configured for email/password, Google sign-in, and TOTP
  through Firebase Authentication with Identity Platform.
- A Firebase Admin service-account key and a default Firestore database.
- A Qdrant Cloud collection with cloud inference available.
- An API key for the selected generation provider and access to its configured model.
- Internet access for cloud services and the first Whisper model download.
- A browser supporting AudioWorklet and microphone access on localhost or HTTPS.

## 1. Install dependencies

```powershell
git clone https://github.com/Vinit-Rabadiya/parenting-voice-assistant.git
cd parenting-voice-assistant
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci --include=optional
npm.cmd --prefix frontend ci --include=optional
```

`requirements-dev.txt` includes the runtime, data-preparation and offline speech-evaluation requirements.
It also installs lint and test tooling; `requirements.txt` is the runtime install.
Root npm dependencies install the Husky development hooks.

Python requirement files pin direct package versions. Update them deliberately,
check a clean installation, and run the application checks before accepting an
upgrade. These files are not a complete transitive lock: indirect Python packages
can still resolve differently across platforms or later installations. The optional
`requirements-evaluation.txt` stack belongs in a separate environment. For Node
packages, use `npm ci` with the checked-in root and frontend lockfiles.
The root `glob` and frontend `minimatch` overrides retain patched indirect
dependencies while their parent packages still request older major versions.

Vite and Vitest retain Picomatch for file matching. A local policy disables its
extended glob patterns and regex quantifiers in every locked 4.0.7 parser, including
caller attempts to re-enable them. Standard wildcard and brace patterns remain
available. Installation and frontend commands verify the reviewed parser source
and apply the policy; Docker explicitly applies it after installing with scripts
disabled. A different version or unexpected source stops those commands for review.
This mitigates the affected feature; version-based dependency alerts can remain
until an upstream fixed version is released and adopted.

## 2. Configure environment files

For a fresh checkout, copy the templates:

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

If those files already exist, edit them rather than replacing your existing values.

Backend `.env`:

```dotenv
HOST=127.0.0.1
PORT=8000
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_ADMIN_KEY_PATH=.secrets/firebase-admin.json
STT_MODEL=base
QDRANT_URL=https://your-cluster-url.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION=caregiver_guidance_everyday_v4
COACHING_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODEL=gemini-3.8-flash
```

The documented Uvicorn command explicitly sets the bind address and port. The
`HOST` and `PORT` application settings do not override those command-line options.
If changing the backend port, also update the Vite development proxy target.

Speech recognition uses the `base` model on CPU. The browser explicitly requests
English transcription, without automatic language detection or translation.
Review and edit the transcript before sending; submitted text passes through the
same language safety gate as typed messages.

For an offline WER and speed benchmark of the unchanged pretrained model, see
the [speech evaluation and recording pack](../eval/stt/README.md). The optional
evaluator produces JSON evidence and a Markdown report for the project document.
Kenyan-caregiver accuracy remains unmeasured until representative recordings and
verified reference transcripts are collected.
Review the transcript before sending. Recognition accuracy and processing time
depend on the recording and hardware. Restart the backend after changing
`STT_MODEL`.

For verification, `npm.cmd run lint` runs only Python/frontend lint and
`npm.cmd test` runs only Python/frontend tests. `npm.cmd run check` retains the
full lint, test, and frontend-build sequence used by the pre-push hook.

Gemini Flash Lite is the default coaching model in single-provider mode. If it returns a quota error (429),
the backend tries the fallback once with identical context and references.
Leave `GEMINI_FALLBACK_MODEL` empty to disable fallback. Each model receives one
SDK attempt; other errors do not trigger fallback. Fallback availability depends
on its own quota and does not guarantee lower latency. Restart the backend after
changing these settings. The selected model is recorded in technical logs.

For Groq, set `COACHING_PROVIDER=groq`, `GROQ_API_KEY` and
`GROQ_MODEL=qwen/qwen3.8-27b` in the private root `.env`. Groq uses pooled HTTPS
requests with reasoning disabled for this model. `GROQ_FALLBACK_MODEL` defaults to
empty. Cross-provider switching is enabled separately as described below. No billing is enabled by these settings.
Groq has its own request/token limits; a faster model does not guarantee a five-second
complete browser request. Switching providers changes the privacy-notice version
and requires acceptance before further processing. Groq data-term and non-personal
testing confirmations are separate from the Gemini flags; see `.env.example`.

Set `COACHING_PROVIDER_FAILOVER=true` to use both services. `COACHING_PROVIDER`
sets the preferred provider; the other becomes its backup. Both API keys and
models must be configured, and production requires processing confirmations for
both. For example, selecting Groq makes Gemini its backup in this mode.
The updated notice names both services, so an existing single-provider acceptance
must be renewed once. Switching between the two after that does not require
another acceptance. Health-note availability requires both providers' independent
processing confirmations; each provider rechecks its own gate before prompting.

On HTTP 429, the backend immediately tries the other eligible provider within the
same request, with the same permitted context and references. Each provider is
attempted at most once per request; the same-provider fallback-model settings are
ignored while cross-provider mode is enabled. No retry sleep is added. A limited
provider is skipped on following requests until its retry metadata permits a
retry, or for `COACHING_PROVIDER_COOLDOWN_SECONDS=60` when no valid delay is given.
Cooldowns are bounded to one day and stored per server process for these two
providers only; they are not user quotas or Firestore usage counters.

If streaming has started, a `reset` event removes the old preview before the
backup begins. Both prefixes are checked independently, and only the final
reviewed answer is persisted. A safety refusal, invalid request, authentication
failure or non-quota error does not trigger switching. If neither provider is
eligible or both reach their limits, the app reports generic temporary
unavailability without exposing provider quota descriptions. Automatic switching
cannot guarantee an answer when both services are unavailable, and the backup's
network and generation time still apply. Restart after changing these settings.

Place the Admin JSON key at the configured path. The service account must belong
to the configured Firebase project and have the required Firestore permissions.
The root `.env` and `.secrets/` directory are excluded from Git.

Frontend `frontend/.env.local`:

```dotenv
VITE_FIREBASE_API_KEY=your-firebase-web-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-project-id.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_APP_ID=your-firebase-web-app-id
```

Use the Firebase Web App configuration, not the Admin private key. Restart the
backend after changing its environment settings and restart Vite after changing
frontend settings.

## 3. Configure Firebase and Firestore

In your Firebase project, enable Email/Password and Google authentication and add
`localhost` as an authorized domain. Enable Identity Platform support for TOTP.

Enable the Cloud Firestore API and create the default Firestore database in
production mode. Backend Admin SDK operations use service-account authorization;
the frontend does not write profiles or feedback directly.

Conversation listing requires the composite index recorded in
`firestore.indexes.json`: collection `conversations`, collection scope,
`child_id` ascending and `updated_at` descending. Create this index in the
Firestore console before using conversation history. The file records the index
definition; starting the backend does not create or deploy it.

Enable TOTP using the included administration script:

```powershell
node --env-file=.env scripts/enable-firebase-totp.mjs
```

To inspect TOTP configuration without changing it:

```powershell
node --env-file=.env scripts/check-firebase-auth.mjs
```

Email verification is required. Google sign-in uses Firebase's verified-email status;
the application never marks an email verified based only on the provider name.
MFA is optional for ordinary accounts. In **My Account**, enable an authenticator,
add a backup on a separate device, or turn MFA off after confirming sign-in.
Adding a first or backup authenticator requires confirming the current sign-in
before a setup key is created. If the QR code cannot be displayed, use the same
key for manual setup. Expired setup requires a fresh sign-in confirmation.
Cancelling setup clears its key and code without changing enrolled authenticators.

`AUTH_REQUIRE_MFA=false` is the default. Set it to `true` to require MFA globally.
The server-issued `mfa_required=true` claim and the `feedback_summary_admin=true`
administrator role also require MFA. Required MFA cannot be disabled through account
settings or bypassed by unenrolling directly with the provider. Protected application
data remains inaccessible until the required MFA sign-in is complete. Security
settings remain available for setup after verified first-factor sign-in.

Disabling MFA removes enrolled factors and invalidates existing sessions. Firebase
remains responsible for validating credentials; the backend verifies token validity,
revocation, current factor enrollment and applicable policy. Keep the deployed site
on HTTPS and restrict Firebase authorized domains to the deployed application.

`AUTH_SESSION_CACHE_TTL_SECONDS=60` reuses a successful remote revocation and
MFA/role check for the same caregiver ID token on ordinary chat, transcription,
feedback and selected read endpoints. Every request still verifies its JWT
signature, issuer, audience and expiry through Firebase Admin; the SDK caches
public signing certificates, whose refresh can still require a network call.
Reuse expires at the earlier of the token expiry or the configured interval from
the start of the fresh check. Cache hits do not extend this interval. A new token
requires a fresh check. Set an integer from `0` to `18000` and restart the backend;
`0` restores fresh remote checks on every request.

An earlier local latency experiment used `AUTH_SESSION_CACHE_TTL_SECONDS=18000`
(five hours); the default and example remain 60 seconds. The effective lifetime
is still capped by the current ID token's expiry. Firebase ID tokens normally
last one hour, and a refreshed token triggers fresh checks in this application.
This setting therefore does not create a five-hour token or skip checks across
token refreshes. Longer reuse also delays detection of external account/policy
changes until token expiry, cache invalidation or the configured interval.

External revocation, account disabling, email-verification changes and MFA/role
changes can take up to this interval to affect ordinary caregiver requests.
Administrator sessions, administrator endpoints, account-security reads/changes,
deletions, profile mutations and routes outside the explicit allowlist always
use fresh remote checks. A fresh account-security lookup invalidates the user's
cached checks; MFA changes and account/data deletion also invalidate on completion
or failure. An in-flight request may already have passed authorization. These
caches are independent per server process, so external changes in another process
are bounded by the same interval. Global mandatory MFA remains enforced on every
request. Consent and ownership checks are never cached here.

The process-owned cache holds at most 256 entries, with keyed token digests,
account IDs, token expiry and MFA/role booleans only. It retains no raw tokens,
messages, profiles or audio, and clears at shutdown. Failed verification or MFA
checks do not create reusable sessions. This is an explicit freshness/latency
tradeoff, not immediate revocation for every ordinary chat request.

For a lost authenticator, choose the backup in the sign-in challenge. If all factors
are lost, an administrator must independently verify account ownership before using
the recovery tool on a trusted workstation with Firebase Admin credentials:

```powershell
.\venv\Scripts\python.exe -m scripts.reset_account_mfa --uid ACCOUNT_UID
.\venv\Scripts\python.exe -m scripts.reset_account_mfa --uid ACCOUNT_UID --apply --identity-verified
```

The first command previews the operation. Recovery resets factors and revokes
sessions without removing mandatory MFA policy; affected accounts must enroll again
before accessing protected data. A password reset alone does not remove MFA.
The backend uses the Identity Platform administration API for enrollment status and
removal because the Python Admin SDK does not expose TOTP management. The service
account needs `firebaseauth.users.get` and `firebaseauth.users.update` permissions.

## 4. Prepare the reference index

The source inventory is in `data/sources.json`. Obtain the matching PDFs and place
them in `data/raw/pdfs/` using the filenames in that inventory. Source documents,
generated passages, and local credentials are not included in the repository.

An existing populated `caregiver_guidance_everyday_v4` collection can be used
without rebuilding. All 216 remote payloads were checked against the local
release fingerprint before activation. Restart the backend after changing
`QDRANT_COLLECTION`; an explicit value in `.env` overrides the default.
To roll back, set `QDRANT_COLLECTION=caregiver_guidance_everyday_v3` and restart.
Neither activation nor rollback deletes a collection.

For a new original 106-passage baseline index, run:

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_rag_data
.\venv\Scripts\python.exe -m scripts.build_rag_passages
.\venv\Scripts\python.exe -m scripts.create_qdrant_collection --collection caregiver_guidance_minilm_v1
.\venv\Scripts\python.exe -m scripts.index_rag --collection caregiver_guidance_minilm_v1 --upload
```

These baseline commands do not build the expanded release. See
[the everyday release instructions](../data/README.md#current-everyday-release)
for the selected release preparation and upload; do not upload the baseline into
the everyday collection. Original selections remain in `data/passage-selections.json`.

## 5. Start the application

Backend terminal:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Wait for **Application startup complete**. The first Whisper load may download
model weights; later loads use the local cache. Use one worker for local use to
avoid loading duplicate speech models.

Frontend terminal:

```powershell
npm.cmd run dev:frontend
```

- Application: http://localhost:5173/
- API documentation: http://127.0.0.1:8000/docs
- Health endpoint: http://127.0.0.1:8000/health/live

Vite forwards `/api/*` to the backend and removes the `/api` prefix. Production
hosting requires an equivalent HTTPS API routing arrangement; Vite's development
proxy is not included in the static build.

### Backend service lifecycle

Both development and production require each enabled provider's API key and
model before startup. With cross-provider failover disabled, an empty provider
fallback-model setting disables that provider's fallback. Missing generation settings stop startup before Firebase initialization
or speech-model loading; error messages name the setting without revealing its
value. Production also applies the [host and provider-term requirements](deployment.md#production-configuration).
These checks validate local configuration, not key validity, quotas or
remote model availability.

Startup creates one coaching and one retrieval service per backend process.
Cross-provider mode owns two lazy coaching clients inside the routing service.
Their synchronous SDK clients open only on first use, with a lock preventing
concurrent first requests from creating duplicate clients. Failed client
construction is not cached, so a later request can retry initialization.
Startup sends no generation request, model-list request or Qdrant query.
The existing speech model still loads during startup.

On shutdown, the application closes internally created coaching/retrieval clients
and clears its service references before deleting the Firebase app. Unused
clients are never constructed just to close them, and clients injected by tests
or scripts remain the caller's responsibility. Partial startup failures follow
the same cleanup path; a client-close failure is logged by service and error type
without preventing cleanup of the other services. Cleanup is shielded from
lifespan cancellation so local resources can finish closing. A later lifespan
creates fresh wrappers. HTTP endpoints use those startup-owned wrappers and
return a generic unavailable response if they are absent.

### Coaching reads and reference cache

For ordinary messages in an existing conversation, the owned profile and bounded
conversation history load concurrently. A conservative safety screen keeps
potential urgent reports on the profile-first path; final safety decisions still
use the actual profile or explicit age. History failures never become empty context.

Each retrieval service keeps up to 128 successful, nonempty reference results in
memory for 60 seconds. Lookup keys use a keyed hash of the complete search text,
exact age inputs, routine, search limits, collection, corpus revision and review
mode. The cache contains copied source passages, not questions, profiles or generated
answers. Cached passages retain their source links and applicability conditions.
Different questions normally require a fresh search; caching does not shorten
generation or guarantee a complete response within five seconds.

`RETRIEVAL_CACHE_TTL_SECONDS=0` disables caching; permitted values are 0–300 seconds.
After changing sources or review status within the same collection, change
`QDRANT_CORPUS_REVISION` and restart every backend instance, or call the service's
`clear_cache()` when updating it in-process. Without invalidation, earlier results
can remain usable until their TTL expires. Errors and empty searches are not cached;
expired results are not returned during an outage. Shutdown clears the cache.
Coaching and retrieval evaluation commands disable it so repeated test questions
still measure actual retrieval.
