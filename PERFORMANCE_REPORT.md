# Application performance review

Date: 3 November 2026 (Africa/Nairobi). Baseline source: `f7412ed`.

The recorded optimized experiments predate consolidation with the earlier
chat-navigation changes. Build sizes and benchmark timings below describe that
measured snapshot, rather than a new measurement of the combined branch.

Eight targeted changes reduce request round trips, database RPCs, connection churn,
frontend work and asset transfers. No dependencies, database indexes, environment
values or hosting resources were changed. These changes are local and have not
been deployed.

The evidence establishes faster **local, controlled request paths**. It does not
establish production response times, model latency, speech accuracy, browser Web
Vitals or deployed query execution plans. No live account records, provider
generation requests or production writes were used for these experiments.

## A. Bottlenecks found

Priority reflects the affected workflow and avoidable work, rather than an
unmeasured claim about which cloud service dominates production latency.

| Priority | Location | Root cause and impact | Evidence |
| --- | --- | --- | --- |
| High | `frontend/src/services/api.js:27`, `hooks/useAccountAccess.js`, `components/PrivacyConsent.jsx`, `components/ChildProfiles.jsx` | Startup separately requested account access, consent and children. Each request repeated token revocation and current account-policy checks. The backend already provided `/me/startup`, including parallel consent/profile reads, but the UI did not use it. | Three requests and three authentication/policy checks become one of each; the real UI/API integration test checks the request paths. |
| High | `frontend/src/hooks/useConversations.js:80` | A first message first created a conversation, then called coaching. Coaching read that newly empty conversation and its messages. The existing `start_conversation` request option was unused. | Two HTTP requests become one; the empty history reads disappear. Transactional answer storage remains. |
| High for report growth | `backend/services/feedback_summary.py:56` | Administrator reporting performed one serial consent-document RPC per distinct account with feedback, up to 500 accounts. This consumed the existing ten-second report budget as account count grew. | The pre-change 100-account experiment performed 100 consent RPCs. The new path performs one batch RPC. The two collection scans remain. |
| High for uncached/repeat loading | `backend/core/frontend.py:11`, `backend/core/http_security.py:73` | The container static host had no compression, and security middleware applied `no-store` to content-hashed JS/CSS as well as private responses. | Baseline initial JavaScript was 463,059 bytes. The new host's actual gzip bytes and cache headers are recorded in `optimized.json`. |
| Medium | `backend/services/account_security.py:12`, `backend/core/security.py:107`, `backend/main.py` | Each account-policy lookup constructed and closed an `AuthorizedSession`, preventing transport reuse. Account policy is checked on every protected request. | A real loopback HTTP experiment measures 100 TCP connections for 100 old-style calls, versus one for 100 serial pooled calls. Both execute all 100 lookups. |
| Medium | `frontend/src/components/GuidanceWorkspace.jsx`, `hooks/useConversations.js` | Loading conversation history hid the entire composer. Selector remounts reloaded the same child list on initial chat entry and profile switching. | A pending-history test now sends and receives a first answer before history resolves. Integration tests verify one profile request across the initial flow and quick profile switches. |
| Medium for long threads | `frontend/src/components/GuidanceAnswer.jsx:118` | Every composer/sidebar parent render re-executed unchanged answer components, including answer parsing, feedback controls and audio hooks. | With 50 saved answers, 20 draft edits cause zero additional answer-text renders. Changing one answer causes exactly one additional render. No browser-frame-time improvement is claimed. |
| Low | `frontend/src/pages/AccountPage.jsx:247` | QR generation code was imported into the initial bundle even when authenticator enrollment was never opened. | Production build now puts QR code generation in a separately requested 23,456-byte chunk. |

### Review of the rest of the request lifecycle

- **Database:** Firestore owns the shared client/channel; there is no SQL pool or
  relational join layer. Conversation lists use a child equality filter, descending
  update time, a limit and an owned cursor. The matching composite index is already
  declared in `firestore.indexes.json`. Message lists order by sequence and use
  bounded cursor pagination. Transactional turn saves recheck both conversation
  and child ownership/deletion state. These protections were retained. The batch
  reporting change reduces RPCs, not the number of billed consent document reads.
- **Retrieval:** `backend/services/retrieval.py` already owns a lazy shared Qdrant
  client, filters age before ranking, rejects unsuitable metadata, and caches only
  successfully filtered public passages. Its cache has a TTL, revision key,
  invalidation epoch, 128-entry limit and defensive copies. Index creation already
  covers four numeric source-age fields in `scripts/create_qdrant_collection.py`.
  No missing index was demonstrated, so none was added or deployed.
- **Authentication:** `backend/core/security.py` still verifies tokens with
  `check_revoked=True` and reads current account policy on every protected request.
  MFA, verified email, account roles and administrator restrictions are unchanged.
  Transport reuse does not cache an authentication result.
- **Middleware and async work:** Blocking SDK operations already run through
  worker threads. The existing body limits and upload timeout remain. The app has
  no runtime background-job queue. Answer persistence remains on the request path
  so a successful normal reply still represents a saved turn.
- **Generation and safety:** Gemini/Groq clients, provider errors/fallback,
  bounded conversation context, local references, input checks and post-generation
  safety review were inspected. No model, prompt, evidence threshold, generation
  policy or safety behavior was changed for speed.
- **Voice and resource ownership:** The microphone worklet batches samples and
  limits capture to 30 seconds; recording hooks release tracks, ports, timers and
  audio contexts. Whisper is loaded once, uses CPU INT8 with bounded threads, and
  permits one inference at a time with immediate busy rejection. WAV validation
  remains. There was no measured basis to trade transcription accuracy for speed.
- **Assets and dependencies:** The interface predominantly uses CSS/inline SVG,
  so no large image conversion was indicated. Vite build output and runtime/dev
  dependencies were reviewed. No package upgrade or new dependency was needed.
- **Configuration:** Container construction, one-worker model ownership,
  development proxying and production security validation were inspected. Existing
  environment files and unrelated local configuration changes were preserved.

## B. Optimizations implemented

| Files modified | Implementation and reason |
| --- | --- |
| `frontend/src/services/api.js`, `hooks/useAccountAccess.js`, `pages/LandingPage.jsx`, `components/PrivacyConsent.jsx`, `components/GuidanceWorkspace.jsx`, `App.jsx` | Use the existing verified startup response, validate its account/consent/profile shape, and pass initial data into the workspace. Account changes, consent challenges and application-data deletion invalidate the initial data. Standalone workspace loading still works. |
| `frontend/src/components/ChildProfiles.jsx`, `components/GuidanceWorkspace.jsx` | Retain the latest profile list across selector remounts. Create/edit/delete responses update that list immediately. Remount reuse expires after 60 seconds; later switches fetch fresh profiles. The server still reloads the child for guidance. |
| `frontend/src/hooks/useConversations.js`, `components/GuidanceWorkspace.jsx` | Create a UUID conversation through the first coaching request. Render the composer independently of history. Merge late history without dropping a new conversation or restoring a deleted one. After an ambiguous first-request failure/cancellation, check whether its conversation exists before a later user-initiated send; coaching is never automatically retried. |
| `backend/services/feedback_summary.py` | Collect bounded, sanitized feedback candidates, then fetch consent in batches of at most 100 with the existing field projection. Match unordered replies by exact document path. Missing documents deny sharing; incomplete, duplicate, unexpected or failed batches fail the report. Retain account/scan/time budgets and all consent-date/version checks. |
| `backend/services/account_security.py`, `backend/core/security.py`, `backend/main.py` | Own one account-security service per application lifespan and retain at most eight idle authorized sessions. Each session is exclusively borrowed by one worker; concurrent calls never use the same session. Failed transports are discarded; shutdown closes idle sessions and closes active sessions when returned. Administrative scripts retain their existing one-shot default. |
| `backend/core/frontend.py`, `backend/core/http_security.py` | Apply gzip only to public static responses. Permit one-year immutable caching only after the static host successfully resolves content-hashed JS/CSS. HTML, unversioned worklet files, errors and private APIs retain `no-store`. Both Windows and POSIX static paths are handled. |
| `frontend/src/components/GuidanceAnswer.jsx` | Memoize unchanged answer components while preserving updates for changed message content, active state, feedback permissions and playback preferences. |
| `frontend/src/pages/AccountPage.jsx` | Import QR generation only when enrolling an authenticator; keep existing error and account-change handling. |

Additional files:

- `scripts/benchmark_performance.py`: reproducible offline request, allocation,
  transport, static-transfer and feedback-report experiments.
- `tests/test_account_security_pool.py`: reuse, fresh policy, thread exclusivity,
  idle limits, failures and shutdown.
- `tests/test_feedback_summary.py`, `tests/test_frontend_hosting.py`,
  `tests/test_service_lifecycle.py`: batch privacy/failure handling, compression,
  caching boundaries and lifecycle cleanup.
- `tests/frontend/performance.test.jsx`, `ChildProfiles.test.jsx`,
  `ConversationWorkflow.test.jsx`, `GuidanceWorkspace.test.jsx`,
  `PrivacyConsent.test.jsx`, and `tests/workflow_app.py`: rendering, bootstrap,
  edited-profile freshness, real UI/API workflows and race/cancellation behavior.

### Runtime and rollout impact

The next build serves compressed public assets and allows browsers to retain
versioned JS/CSS for a year. New builds change their URLs; HTML remains fresh.
Compression adds some CPU work on uncached static transfers. The authentication
pool retains up to eight idle sessions per process and imposes no new waiting
queue. QR enrollment makes a small additional chunk request when first opened.
These are code-level runtime changes; no production configuration was edited.

## C. Performance comparison

All times below are milliseconds. Each cell is **before -> after**.

| Workflow | Mean | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: |
| Base startup chain (history/remount fetches excluded) | 72.379 -> 25.481 | 71.490 -> 24.639 | 79.324 -> 28.647 | 89.507 -> 46.147 |
| First message, including conversation creation/save | 106.227 -> 71.756 | 104.714 -> 71.617 | 115.200 -> 77.456 | 130.244 -> 79.216 |
| Feedback report, 100 accounts | 171.538 -> 6.353 | 170.194 -> 6.137 | 184.021 -> 7.520 | 186.925 -> 7.669 |

Measured operation counts:

| Operation | Before | After |
| --- | ---: | ---: |
| HTTP requests in base startup chain | 3 | 1 |
| Token revocation / current-policy checks in that chain | 3 / 3 | 1 / 1 |
| HTTP requests for a first message | 2 | 1 |
| Reads of an empty conversation parent / message query | 1 / 1 | 0 / 0 |
| Consent RPCs for 100 report accounts | 100 individual | 1 batch |
| Consent documents read for that report | 100 | 100 |
| TCP connections for 100 serial account-policy lookups | 100 | 1 |
| Actual account-policy lookups in that transport experiment | 100 | 100 |

The transport experiment measured the following local HTTP times:

| Session mode | Mean | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: |
| Per-call session (legacy behavior) | 9.915 | 5.080 | 26.976 | 31.295 |
| Pooled session | 2.804 | 2.711 | 3.633 | 4.434 |

Production-build and standalone-host transfer evidence:

| Metric | Before | After |
| --- | ---: | ---: |
| Initial JS, uncompressed bytes | 463,059 | 442,751 |
| Initial JS bytes served by standalone host (gzip-capable client) | 463,059 | 131,499 |
| QR chunk in initial load | Included in entry bundle | Deferred (23,456 raw / 8,740 gzip bytes when needed) |
| Hashed asset cache policy | no-store | public, max-age=31536000, immutable |
| HTML / unversioned worklet / private API cache policy | no-store | no-store |

Code splitting reduces initial JavaScript by 4.4% in raw bytes. It adds chunk-loader overhead to total built JavaScript; it does not remove the QR feature. The combined splitting/compression change reduces this standalone initial JS transfer by 71.6%. Neither percentage is a browser load-time or production-latency claim.

Supplemental CPU/allocation measurements use the paired legacy and combined controls from the optimized run, not the earlier baseline:

| Path | Process CPU ms/sample: legacy -> combined | Python traced peak bytes: legacy -> combined |
| --- | ---: | ---: |
| Startup | 27.656 -> 8.281 | 78,808 -> 49,984 |
| First message | 37.656 -> 21.562 | 88,382 -> 79,574 |

The render regression test records 50 initial answer-text renders, still 50 after 20 draft edits, and 51 after updating one saved answer. The pending-history test verifies composer availability with an unresolved history request; no wall-time saving is extrapolated from that intentionally stalled request.

Raw records: [baseline](artifacts/performance/baseline.json), [optimized](artifacts/performance/optimized.json), [feedback baseline](artifacts/performance/feedback-baseline.json), [feedback optimized](artifacts/performance/feedback-optimized.json).

### Method and practical limits

The initial baseline was captured before application changes. Experiments use
Python 3.13.7 on Windows, FastAPI's in-process `TestClient`, synthetic accounts,
and the application's real routing, validation and processing logic with injected
IO boundaries. The request benchmark assigns **5 ms per fake external operation**;
it does not simulate real cloud latency or a language model. The feedback
experiment uses **100 synthetic accounts and 1 ms per fake database RPC**.

Request and transport scenarios have 100 samples each; reporting has 30 samples.
P50 is the median; P95/P99 use the lower empirical order statistic. These small
samples illustrate local behavior and are not production tail-latency SLOs.
The optimized request run also repeats legacy-path controls in the same process.
The loopback transport experiment uses actual HTTP/TCP with anonymous credentials,
and includes the pooled path's first cold call; it has no TLS or real identity
provider. Its timing is not a TLS-handshake or Internet-latency estimate.

CPU measurements are per-sample process CPU time. Python allocation peaks are a
separate single traced sample per path, excluding tracing overhead from timed
runs. They are not process RSS, peak deployment memory or native Whisper memory.
Static gzip bytes come from raw encoded responses from the actual new host.
The old standalone host's transfer size is its built file size; a deployed proxy
could already apply compression, and that was not measured.

### Validation

Recorded baseline: `npm.cmd run check` passed **1,315 backend tests, 238 UI tests, seven audio
tests**, Python/frontend lint and the production build.

Recorded optimized snapshot: the same complete check passed **1,333 backend tests, 254 UI tests, seven
audio tests**, both linters and the production build. A focused rerun also passed
all 17 profile tests. `git diff --check` passed. These counts describe the measured
snapshot before consolidation with the earlier navigation changes.

Reproduce from the repository root with the installed environment:

```powershell
npm.cmd run check
.\venv\Scripts\python.exe -m scripts.benchmark_performance --output artifacts/performance/optimized.json
.\venv\Scripts\python.exe -m scripts.benchmark_performance --feedback-only --samples 30 --io-delay-ms 1 --output artifacts/performance/feedback-optimized.json
```

The recorded pre-change feedback results are retained separately; rerunning the
current feedback implementation measures the new batched implementation.

## D. Remaining bottlenecks and uncertainty

1. **External generation latency is unmeasured here.** Model execution, token
   counts, provider load, fallback and network location may dominate actual
   answers. Existing request IDs, `Server-Timing`, stage logs and generation token
   logs can separate those costs in an authorized deployed test. The local gains
   remove overhead but do not establish faster model inference.
2. **Two identity lookups can still occur within one protected request:** Firebase
   revocation verification and the current MFA/role lookup. The latter reads data
   the public Admin SDK verification result does not expose. This review reduced
   requests and reused transports instead of weakening freshness/security or
   coupling to private SDK internals.
3. **Administrator reporting still scans up to 10,000 projected documents per
   group across two groups.** Batching removes the consent N+1 RPC pattern, but
   not scan cost or document read charges. At larger scale the existing budgets
   deliberately return an error rather than partial counts.
4. **Profile lists are not paginated, usage display performs two document reads,
   and recursive deletion can be slow for large accounts.** Limits on profile
   creation do not impose a lifetime profile count. These paths were reviewed,
   but no production volume/query measurements justified broader schema or
   deletion-workflow changes in this pass.
5. **Whisper latency, native CPU/RSS and simultaneous voice capacity need a
   representative speech/load corpus on the target host.** Model changes or more
   workers would affect accuracy, memory and concurrency; none was made blindly.
6. **Guidance is returned after complete generation and safety review.** The
   earlier navigation changes remove the post-response reveal delay and render
   checked answers immediately. They remain in the combined branch. Streaming raw
   provider tokens would bypass the current full-answer safety review.
7. **The Firebase auth runtime and other application screens remain in the entry
   bundle.** This pass splits QR generation only. Older messages loaded through
   repeated pagination can still grow the mounted thread; memoization reduces
   update work but does not virtualize that history.
8. **Live query plans, index deployment state, browser navigation timings,
   Internet TTFB, production P95/P99 and peak load were not measured.** No claim
   about deployed speed, active cloud indexes or production bottleneck ranking
   is made from the offline data.

## E. Recommendations

1. In an authorized staging session, measure typed first turns, follow-ups,
   local-reference answers, fixed safety replies, recorded speech, history and
   account/report operations separately. Correlate browser time with the existing
   anonymous request/stage IDs. Use synthetic or otherwise approved content.
2. Collect a larger warm/cold sample on the target deployment, including the
   intended concurrent tester load. Record model/retrieval/auth/Firestore/save
   latency and native CPU/RSS before selecting model, region or capacity changes.
3. Verify the existing Firestore composite index and Qdrant age indexes on the
   actual collections, then inspect measured query plans/read counts before
   adding indexes. The local index definitions alone do not verify deployment.
4. If reporting grows beyond its current budgets, evaluate indexed feedback-only
   reads or maintained aggregates with deletion and consent-withdrawal semantics.
   A materialized report must not outlive permission to share its comments.
5. If browser profiling identifies initial parse/execute time as material, split
   account/admin/auth screens with loading and chunk-failure recovery. If long
   histories cause layout cost, evaluate thread virtualization without losing
   accessibility, scroll position or playback state.
6. If true streaming is needed, design incremental safety and consistent storage
   first. Keep the existing full-response checks until an equivalent design is
   validated.

## Follow-up: reported localhost question timings

The user supplied five response-time observations and confirmed they came from
the local application. These are application observations rather than the
synthetic benchmark above. Individual stage durations and the running backend's
revision were not captured with the original transcript.

| Test topic | Application result | Reported seconds |
| --- | --- | ---: |
| Complementary feeding and choking precautions | False emergency escalation; no model generation | 4.57 |
| Sleep and caregiver coordination | Generated guidance | 7.21 |
| Bilingual play and development | Generated guidance | 8.60 |
| Transitions and frustration | Generated guidance | 7.24 |
| Flexible everyday developmental activities | Generated guidance | 7.87 |

The **four generated replies** average **7.73 seconds**, with a median of
**7.555 seconds** and range **7.21–8.60 seconds**. There are too few uncontrolled
observations to estimate P95/P99. The earlier synthetic millisecond results must
not be substituted for these application observations.

### Reproduced routing bug and correction

`backend/services/input_safety.py` treated every occurrence of `choking` as an
incident unless a narrow negation/prevention prefix immediately preceded it.
The exact feeding prompt matched the `choking` rule solely through the phrase
`choking precautions`. This also made the first observation unsuitable as a
generation-latency test.

The correction recognizes specific prevention noun phrases such as `choking
precautions`, `choking prevention`, `choking hazards` and `choking risks`, at the
individual match. Actual/ambiguous active-report wording stays conservative;
another danger sign anywhere in the message still takes priority. No model call
is used to make this routing decision. The exact 910-character prompt now passes
both the initial youngest-age screen and the resolved-age screen without an
emergency flag.

New unit cases include prevention topics, mixed prevention/active reports and
malformed active wording. API regressions verify that preventive feeding reaches
generation/storage, while an active choking report bypasses generation. All 60
existing fixed danger-sign evaluation cases still pass with 30 true positives,
30 true negatives and zero false positives/negatives on that development set.
That fixed set is not independent clinical validation.

### Diagnosing the remaining seconds

The 4.57-second fixed response demonstrates that this particular run incurred
delay without retrieval or generation. It does not identify that delay as
Firestore, authentication, startup, networking or persistence. Subtracting it
from a different generated request would not measure model time: the paths,
cache/connection state and operations differ.

The backend now exports bounded, fixed-name stage durations in the existing
`Server-Timing` response header, alongside the total `app` duration and existing
random `X-Request-ID`. These cover token verification, current account security,
consent, profile/history reads, usage-limit enforcement, retrieval, generation,
response review and saving. Only measured stages appear. Parallel stages can
overlap, so their durations should not simply be summed. Durations are in
**milliseconds**. Headers contain no question text, tokens or account/child IDs.
The JSON response contract and user-facing response-time display are unchanged.

With the updated backend running, open browser Developer Tools → Network, send
one question and inspect the `POST /api/coach` response headers. Compare
`generation` with the authentication, database and save stages over repeated
fresh-chat and follow-up tests. Restart the local backend if it is not watching
source changes. No live latency improvement or deployment is claimed from this
correction.

Follow-up verification: the full `npm.cmd run check` passed **1,354 backend tests,
263 UI tests and seven audio tests**, both linters and the production build.
The 250 focused safety/conversation/header tests also passed. A local HTTP probe
confirmed the running backend exposes the new stage metrics and rejects an
invalid bearer token with HTTP 401; it did not use a real account or invoke a
model. A new signed-in request's stage timings are still needed to attribute the
reported 7–9 seconds. The `.env` file and production deployment were not changed.

### Local capture without Developer Tools (4 November 2026)

Development mode supports a single local timing capture. Arm it for the running
backend's port by creating `tmp/capture-next-coach-timing` containing
`{"server_port":8000}`. After a coaching response completes on that port, the
backend consumes the marker and atomically replaces
`tmp/local-coach-timing.json`. Requests on other ports cannot consume the marker,
so synthetic workflow servers and ordinary TestClient requests cannot overwrite
the requested live observation. The capture is disabled in production.

The file contains only the random request ID, fixed route, HTTP status, total
server duration and fixed-name stage durations. It contains no question, answer,
authentication token or account/child identifier. File writing runs in a worker
thread after the response has been sent. No further requests are recorded unless
capture is armed again. A new real observation has not yet been captured.

The resumed verification also corrected Windows path matching for the existing
`/chat/{id}` bookmark shell and made the conversation workflow test wait for an
in-flight reopen before clicking its disabled menu button. The 199 focused
backend cases and all six UI/API workflow tests passed after these corrections.

The final resumed `npm.cmd run check` passed **1,365 backend tests, 263 UI tests
and seven audio tests**, both linters and the production build. The local backend
and Vite frontend were then started and their health/proxy routes verified. An
unauthenticated HTTP 401 probe verified that capture works on the real local
backend; its record is explicitly marked as a connectivity check, not a live
guidance latency measurement. Capture was rearmed for the next signed-in request.

## First captured signed-in request (4 November 2026)

The automatic local capture recorded HTTP 200 with **11,191.6 ms** of total
server time. This is a real signed-in application observation, not a synthetic
delay experiment. The capture stores no prompt, answer or account/profile ID.

| Stage | Milliseconds |
| --- | ---: |
| Token verification | 399.2 |
| Current account security | 406.4 |
| Consent read | 397.3 |
| Profile lookup | 1,075.6 |
| Conversation context | 1,917.3 |
| Usage-limit transaction | 2,647.8 |
| Reference retrieval/local selection stage | 0.2 |
| Generation | 2,312.8 |
| Response safety review | 7.7 |
| Interaction-save transaction | 2,970.7 |

Profile and history reads overlap. Counting the longer history branch once,
database-related stages occupy approximately **7,933.1 ms (70.9%)** of this
request's critical path. Generation occupies **2,312.8 ms (20.7%)** and the two
authentication stages **805.6 ms (7.2%)**. Remaining time includes other checks,
scheduling, middleware and serialization. These are application-stage durations,
including network/SDK/worker waits; they are not database-engine execution plans.
One observation after a local restart does not establish warm-load percentiles.

A read-only Firestore Admin metadata request confirmed that the default database
is in **`nam5`**, the US Central multi-region described in the
[official location reference](https://firebase.google.com/docs/firestore/locations).
The app was running locally for this measurement. Database round trips are now a
demonstrated latency contributor; geography is a plausible contributor rather
than a measured attribution for every millisecond. Google's
[best-practice guidance](https://firebase.google.com/docs/firestore/best-practices)
recommends locating compute close to the database. No database or hosting location
was changed. A provisioned Firestore database's location cannot be changed in place.

### Targeted transaction improvement

`CaregiverDataService.save_conversation_turn` previously read the conversation
and child through two sequential document RPCs inside the same transaction.
They now use one projected BatchGet RPC within that transaction. Feedback saving
uses the same approach for its conversation and assistant-message checks. Replies
are matched by exact document path because batch ordering is unspecified.
Incomplete, duplicate or foreign replies fail before any write.

The transaction's begin/commit behavior, ownership/deletion checks, message
ordering and atomic writes remain. Tests cover missing/deleting/wrong-child
records and partial batch failures. The read boundary changes from **two RPCs to
one per successful turn save**, while reading the same two documents. This does
not eliminate all transaction round trips or reduce document-read billing.

The distributed usage reservation remains transactional and runs before
generation. Removing it, caching permissions or sending a normal answer before
its durable save would change correctness/security semantics and was not used
as an optimization.

Raw evidence: [signed-in capture before batching](artifacts/performance/live-coach-before-batch.json)
and [read-only database location](artifacts/performance/firestore-location.json).
An after-change signed-in observation is still needed to compare live latency;
the RPC reduction alone is not claimed as a measured wall-time improvement.

### Live read-boundary comparison

A separate read-only experiment compared two sequential document reads with one
batch read of those same two references against the actual configured Firestore
database. The references were random, nonexistent synthetic documents; no
personal records were queried and nothing was written. Five paired samples used
alternating order after an excluded warm-up batch, with retries disabled and the
same five-second deadline on both patterns.

| Read pattern | Mean ms | Median ms | Minimum ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: |
| Two sequential RPCs | 1,418.989 | 1,406.310 | 1,396.851 | 1,457.593 |
| One batch RPC | 641.130 | 392.600 | 301.541 | 1,108.955 |

This demonstrates a faster read boundary on this local-to-Firestore connection.
It excludes transaction begin/commit, write processing and model generation, so
it is not a measured improvement in total reply latency. Five samples are not a
tail-latency guarantee. Raw paired results are saved in
[the live read comparison](artifacts/performance/live-firestore-read-comparison.json).

After the batching change, all **1,369 backend tests**, all **six UI/API workflow
tests**, Ruff and the diff whitespace check passed. The complete frontend suite
(263 tests), seven audio tests, lint and build passed immediately before this
backend-only change. Overall signed-in reply latency after batching remains
pending capture.

### First complete reply after batching

The next signed-in request completed with HTTP 200 and a successful save, but
its **16,247.6 ms** total was slower than the earlier **11,191.6 ms** request.
The observations must not be presented as an overall latency improvement.

| Stage | Before ms | First after-change ms |
| --- | ---: | ---: |
| Token verification | 399.2 | 4,338.2 |
| Current account security | 406.4 | 1,340.1 |
| Consent | 397.3 | 2,054.7 |
| Profile lookup, overlapping history | 1,075.6 | 469.4 |
| Conversation context | 1,917.3 | 2,006.2 |
| Usage-limit transaction | 2,647.8 | 1,979.6 |
| Generation | 2,312.8 | 2,267.5 |
| Interaction-save transaction | 2,970.7 | 1,932.5 |

The observed save stage decreased by **1,038.2 ms**, while authentication increased
by **4,872.7 ms** (805.6 → 5,678.3 ms). Database-related critical-path time stayed
approximately level (7,933.1 → 7,973.0 ms) because consent became slower as other
database stages became faster. Generation remained about 2.3 seconds.

Process metadata confirmed the backend worker restarted after the Python change.
Whether the request was its first authenticated call is not established, so cold
initialization and network variation are hypotheses rather than a proven cause.
A further warm observation is being requested without another code reload.
The raw record is saved in
[the first after-change capture](artifacts/performance/live-coach-after-batch-first.json).

### Repeat without a further code change

The requested repeat completed with HTTP 200 in **12,022.3 ms**. No Python code
was changed by this agent between these two after-change observations.

| Stage | Original ms | First after-change ms | Repeat ms |
| --- | ---: | ---: | ---: |
| Total server response | 11,191.6 | 16,247.6 | 12,022.3 |
| Authentication, combined | 805.6 | 5,678.3 | 2,581.0 |
| Consent | 397.3 | 2,054.7 | 1,755.4 |
| History, overlapping profile | 1,917.3 | 2,006.2 | 2,043.0 |
| Usage transaction | 2,647.8 | 1,979.6 | 2,483.0 |
| Generation | 2,312.8 | 2,267.5 | 1,108.4 |
| Save transaction | 2,970.7 | 1,932.5 | 1,949.5 |

The repeat still spent approximately **8,230.9 ms (68.5%)** in database-related
stages, **2,581.0 ms (21.5%)** in authentication, and **1,108.4 ms (9.2%)** in
generation. The faster generation did not make the whole request faster than
the original. An overall improvement is **not established** by these samples.

Save durations remained around 1.94 seconds after batching versus the original
2.97 seconds. The controlled read-only comparison and reduced RPC count support
the read-boundary change, but larger network/service variability remains. Warm
authentication improved from the first after-change sample but stayed above the
original, so a one-off cold initialization cannot explain all remaining delay.

The next architectural comparison should place compute and database close
together, including a benchmark from the intended hosted backend before choosing
a database migration. A nearby PostgreSQL deployment is one option; using the
current Firestore from closer compute is another. Changing the model alone would
leave most of this measured request's waiting time. No database migration,
hosting change, permission caching or removal of quota checks was performed.

Raw repeat evidence:
[after-change repeat](artifacts/performance/live-coach-after-batch-warm.json).
The one-request capture marker has been consumed; further capture is off until
explicitly armed again.

## Caregiver session reuse and usage-limit provenance - 4 November 2026

The project proposal (`docs/VinitRabadiya_149227.docx`, including inspection for
comments) contains no explicit usage/rate-limit or quota requirement. Available
Markdown project notes also provide no supervisor attribution for this feature.
This does not establish what was discussed verbally. Git commit `6913475`
(`feat(api): add per-account usage limits`, 22 October 2026) introduced the
hourly/daily Firestore counters as a separate implementation feature, before this
performance work. Limits are a configurable product/cost safeguard, not a login
requirement or an external provider's quota tracker.

Ordinary accepted coaching attempts still perform one Firestore transaction to
check and reserve hourly/daily usage; rejected or missing-profile requests may
exit before that point. Recognized urgent safety responses bypass this quota.
Child creation has its own quota. Reading account usage does not consume it.
No quota policy, counter storage, `.env` setting or cloud service was changed
in this follow-up.

The earlier samples showed two expensive remote authentication/account checks
for each ordinary request: Firebase token revocation checking and a separate live
MFA/role lookup. Firebase documents that revocation checking requires an extra
network round trip:
[Manage User Sessions](https://firebase.google.com/docs/auth/admin/manage-sessions).

The backend now owns a bounded, thread-safe `AuthSessionCache` per process:

- First access for an ID token retains full Firebase revocation checking and the
  live account-security lookup, with email/tenant/MFA checks before reuse is allowed.
- Ordinary caregiver chat, transcription, feedback and selected reads reuse the
  successful remote checks for at most 60 seconds by default, capped by token
  expiry. Repeated hits do not extend the interval, which starts before the fresh
  verification. Every request still validates the JWT with Firebase Admin;
  certificate refresh can occasionally contact Firebase.
- Administrators, administrator endpoints, security reads/changes, deletions,
  profile mutations and unlisted routes always refresh remote checks. Fresh
  account-security lookups invalidate that user's existing entries. MFA and
  account/data mutations invalidate again after success or failure, and cache
  revisions prevent older concurrent lookups from restoring invalidated entries.
- Entries contain keyed token digests, UID, expiry and MFA/role booleans only,
  with no raw token or family content. Maximum 256 entries; cleared on shutdown.
  Failed verification and incomplete MFA do not populate the cache. Signature
  validation and a second freshness check prevent a slow certificate refresh from
  using an already expired entry.
- `AUTH_SESSION_CACHE_TTL_SECONDS` accepts integer `0..300`, default `60`.
  Restart after changing it; `0` restores fresh remote checks on every request.
  An application without the cache also falls back to fresh checks.

**Changed security freshness:** external revocation, account disabling, email
verification and MFA/role changes can take up to the configured interval to affect
ordinary caregiver requests in each process. Sensitive/administrator requests
remain fresh, global mandatory MFA is applied on each request, and consent,
ownership and usage checks remain independent and uncached. An in-flight request
may already have passed authorization. This bounded tradeoff is intentional in
response to the user's request to reuse an already signed-in session.

Validation: the full backend suite passed **1,422 tests**, with Ruff passing.
The added integration tests exercise both `/coach` aliases with the real auth
and consent dependencies: startup followed by repeated coach calls uses
`check_revoked=True` once, then `False`, and performs one live account lookup.
Each coach call still checks consent and the usage service; withdrawing consent
blocks subsequent processing. Further cases cover expired/revoked/invalid tokens,
TTL boundaries, token/account isolation, MFA/admin enforcement, sensitive endpoint
refresh, invalidation during mutations, cache bounds/concurrency and shutdown.

These are controlled dependency-boundary tests, not a signed-in cloud latency
benchmark. The previously measured 2,581 ms authentication stage identifies the
opportunity; it does not establish the new response time or a fixed saving.
The other measured database stages, including the usage transaction, remain.
Evidence: [backend verification](artifacts/performance/session-auth-backend-check.txt).

## Five-second localhost target - 4 November 2026

The user requested a response around five seconds. Work targeted the same local
development application used for the earlier captures; no hosted deployment,
database migration, model change or external account change was made.

### Changes

1. The coaching dependency loads current consent, the child profile and an
   existing conversation's parent header in one validated, account-scoped
   Firestore `BatchGet`. It checks current consent before interpreting the
   profile or querying messages. The endpoint reuses these snapshots only within
   that request, eliminating duplicate consent/profile/header reads. Follow-ups
   use one subsequent bounded messages query. New conversations omit the parent
   from the initial batch. Save transactions still recheck current ownership,
   existence and deletion flags at commit time. No cross-request profile, consent
   or conversation cache was added.
2. Added explicit `USAGE_LIMIT_BACKEND=memory` for a single development worker,
   and selected it in the local `.env`. This preserves hourly/daily counting and
   atomic enforcement with a process-owned lock, removing the per-message quota
   database transaction. Local counters start empty, reset on backend restart,
   are independent of existing Firestore counters, and are not shared across
   workers. Successful account-data deletion clears the matching local counters.
   Storage is bounded to 1,024 active account/action entries; live counters are
   never evicted to admit additional usage. Capacity exhaustion fails closed.
   `firestore` remains the default and production startup rejects memory mode.
3. The preceding 60-second authentication reuse remains active. Global MFA,
   current consent, ownership and sensitive/admin checks remain enforced as
   documented above. The local timing stage `coaching_documents` now measures
   the combined read; separate consent/profile stages therefore approach zero.

Firebase recommends reducing unnecessary serial reads and placing compute close
to the database, because distant network hops increase latency:
[Firestore best practices](https://firebase.google.com/docs/firestore/best-practices).
The read batching applies in both environments; local memory quotas specifically
do not establish the latency of production Firestore quota enforcement.

### Two real replies after the changes

The user resent the feeding question twice consecutively through localhost.
Both completed with HTTP 200; the metadata capture contains no prompt, answer,
account ID or token. No application source was changed between the captures.

| Stage | First request ms | Warm request ms |
| --- | ---: | ---: |
| Total server response | 8,485.6 | **4,218.4** |
| Token verification | 2,247.4 | 1.5 |
| Live account-security lookup | 758.5 | reused, no lookup |
| Combined consent/profile/header read | 1,820.9 | 980.6 |
| Bounded history query | 491.3 | 509.7 |
| Local usage reservation | 0.5 | 0.4 |
| Model generation | 1,348.7 | 940.0 |
| Durable save transaction | 1,771.6 | 1,772.8 |

The warm request meets the five-second **server-response** target in this
observation. It is **64.9% shorter** than the previous 12,022.3 ms repeat, while
the first request after these changes still takes 8.49 seconds. Its fresh
authentication stages total 3,005.9 ms. This pair does not establish a percentile,
average, browser end-to-end time, or a five-second guarantee after token refresh,
cache expiry, worker restart, network variation or new-conversation creation.
Remote database and model variability also contributed; the entire difference
cannot be attributed to any single change.

The next improvement for consistent fresh-request latency is reducing remote
authentication overhead and benchmarking compute near the current `nam5`
database. The current change reaches the warm local target without moving
durable saving into the background or returning before persistence completes.

Raw captures:
[first](artifacts/performance/five-second-live-first.json),
[warm](artifacts/performance/five-second-live-warm.json).
Capture finished and its one-request markers were consumed; further capture is
off. Verification passed **1,447 backend tests**, **six real UI/API workflow
tests**, and Ruff. Focused tests use the real batching/consent/auth/storage
boundaries with SDK IO replaced, including unordered/incomplete/duplicate/foreign
batch replies, withdrawn consent, changed profile ages, mismatched/deleting
parents, urgent-response history/quota bypass, concurrent quota enforcement,
counter capacity/reset/deletion and service cleanup. The UI workflow fixture now
exercises the new coaching dependency as well.

Verification logs:
[backend](artifacts/performance/five-second-backend-check.txt),
[UI/API workflow](artifacts/performance/five-second-workflow-check.txt).

The existing offline request-path benchmark also completed with 20 samples and
5 ms injected per I/O boundary after updating its fixture for the new batched
dependency. This is a compatibility/structural smoke check: it deliberately uses
fake authentication and quota delay, not the local memory quota/session reuse
configuration, and its timings do not predict live response times.
[Offline benchmark](artifacts/performance/five-second-offline-path.json).
The observed local configuration, target result and limits are recorded in
[the result summary](artifacts/performance/five-second-result.json).

## Usage removal and streamed coaching - 4 November 2026

The user explicitly requested removal of application usage limits and real
incremental replies. This supersedes the earlier Firestore/memory quota modes.
Hourly/daily quota enforcement, counter services, usage dependencies, configuration
settings, `/me/usage` and the My Account Usage panel have been removed. Coaching
and child creation perform no usage check, reservation or counter transaction.
Obsolete usage tests were replaced with a test that sends 35 coaching requests
without a quota or counter-store dependency. External model providers can still
enforce their own quotas; provider HTTP 429 handling remains.

### Streaming behavior

The same authenticated `POST /coach` negotiates SSE with
`Accept: text/event-stream`, while JSON clients retain the complete response
contract. The Groq transport requests `stream=true`, parses real content deltas
and requires a valid terminal finish plus `[DONE]`. Gemini uses
`generate_content_stream` with a per-stream request timeout. Private reasoning
fields are not forwarded. A fallback model can only start before any output
delta, preventing two model answers from being concatenated.

The endpoint retains input triage, consent, ownership, age handling, references,
profile rules and final output checks. It releases complete sentence prefixes
after the existing checks; care-specific rules that need a complete answer hold
that answer for full review. A final safety replacement or provider refusal can
replace an earlier checked prefix. These remain limited pattern safeguards, not
clinical or comprehensive semantic validation. No raw unchecked token stream is
presented as validated childcare advice.

The browser displays incoming text directly, with no artificial word-reveal
timer. `ready` replaces any preview with the fully reviewed answer before the
save finishes. `done` confirms final stored IDs and timing metadata only after
the persistence operation. Feedback and audio remain disabled while pending.
Errors, account changes, timeout and cancellation remove the pending preview;
an interrupted stream cannot confirm a partial answer as saved. A persistence
operation that already started may still finish after browser cancellation, so
the existing instruction to reopen an uncertain conversation remains applicable.
Urgent fixed referrals can also be displayed before their save completes.

The transport uses a bounded 16-event queue with backpressure, a 16,000-character
output bound, finish/truncation checks and cancellation checks on every provider
delta. Iterators and upstream responses close when the worker exits; a stalled
network read remains bounded by its transport timeout. A 45-second deadline is
checked between provider chunks. No background task confirms a save early.

### Verification and live provider probe

`npm run check` passed both linters, **1,436 backend tests**, **280 UI tests**,
**seven audio tests**, and the production build. After correcting stream timing
capture, the complete backend suite passed **1,437 tests**. Tests cover real SSE
provider parsing, Gemini streaming, split unsafe patterns, provider refusals,
truncation, fallback boundaries, checked-prefix replacement, failed saves,
bounded-queue cancellation, split UTF-8, malformed frames, account changes and
quota removal. The UI/API workflow uses an explicit server-side gate: the test
sees a checked sentence while generation is still blocked, then releases it and
verifies that feedback/audio enable only after saving. A second workflow case
cancels after that first sentence and verifies that the preview disappears.

One live Groq/Qwen call used a synthetic non-personal babbling question, with no
database/account data and no answer text stored in the probe artifact:

| Generation-only measurement | Observed |
| --- | ---: |
| First provider content delta, including local client setup | 1,244.6 ms |
| First checked sentence | 1,330.7 ms |
| Complete generation | 1,543.5 ms |
| Provider content chunks | 126 |

This proves the configured provider streams successfully. It does not measure
application authentication, data reads, browser painting or durable saving, and
is not an overall latency guarantee. Streaming reduces time to visible text; it
does not remove initial authentication/database/provider delays.

The first two signed-in SSE captures incorrectly sampled the header boundary
(341.2 and 541.1 ms), omitting later generation and save stages. They are labeled
**header-only** and must not be presented as first-answer or complete-response
latencies. The capture now finalizes after the response body finishes, records
the bounded stream outcome separately from HTTP status, and includes
`generation_first_token`, `first_answer` and save stages. A regression test
verifies that stages absent from early headers appear in the final capture.
`first_answer` measures server-side queuing of checked text, not browser paint.

References:
[Groq streaming](https://console.groq.com/docs/text-chat),
[Gemini Python streaming](https://googleapis.github.io/python-genai/).
Evidence:
[full checks](artifacts/performance/streaming-check.txt),
[final backend checks](artifacts/performance/streaming-final-backend-check.txt),
[live provider probe](artifacts/performance/live-provider-streaming-probe.json),
[first header-only observation](artifacts/performance/streaming-header-only-first.json),
[second header-only observation](artifacts/performance/streaming-header-only-warm.json).

A corrected signed-in first-answer/completion sample has not yet been captured;
no full-application first-text figure is claimed here. The subsequent capture
window closed and capture is off. The generation-only probe and deterministic
UI/API streaming tests above are the available evidence for incremental output.

## Five-hour authentication reuse maximum - 4 November 2026

At the user's explicit request, the local `.env` now selects
`AUTH_SESSION_CACHE_TTL_SECONDS=18000` (five hours). Configuration and cache
validation permit `0..18000`; the fallback default and example remain 60 seconds.
No hosted deployment was performed, and no ID-token expiry or sensitive-route
authorization rule was changed.

This is a maximum reuse interval for the exact verified token. Its expiry still
ends reuse, a refreshed token gets fresh remote checks, cache hits never extend
the interval, and administrator/security/destructive operations remain fresh.
Firebase ID tokens normally last one hour, so normal SDK token refresh prevents
five uninterrupted hours of reuse with the existing token-keyed cache:
[Firebase session management](https://firebase.google.com/docs/auth/admin/manage-sessions).
Expired tokens are never accepted to fill the configured interval. External
revocation, disabling, email/MFA/role policy changes can remain unobserved on
ordinary cached requests until token expiry, local invalidation or the configured
maximum, whichever comes first. This larger freshness tradeoff was disclosed.

Verification passed **132 focused authentication, session, deployment and
lifecycle tests** plus Ruff. Added cases prove reuse beyond the old one-minute
window, rejection at token expiry even with a five-hour setting, a fixed five-hour
cutoff for a synthetic longer-lived token, accepted bounds and rejection above
the maximum. Local configuration loads 18,000 seconds and backend health returns
HTTP 200. No new latency improvement is claimed without measurement.
[Verification log](artifacts/performance/five-hour-auth-check.txt).

## Groq/Gemini quota failover - 4 November 2026

The user requested both providers with automatic switching when one exhausts its
quota. The local `.env` now enables `COACHING_PROVIDER_FAILOVER=true`, with the
configured Groq/Qwen model preferred and Gemini Flash Lite as backup. Both API
keys and independent processing confirmations were already configured; no keys,
billing settings or processing-confirmation values were changed. There was no
hosted deployment.

The process owns one routing service and two lazy reusable provider clients.
On HTTP 429 it immediately tries the other eligible provider, without a retry
sleep, once per provider per request. Same-provider fallback-model retries are
disabled in this mode. Successful requests use only one provider. Each failure
sets a provider-only cooldown: valid `Retry-After` or Gemini `RetryInfo` delays
are honored, bounded from one second to one day; otherwise the configured
60-second cooldown applies. Following requests skip cooling providers. Eligible
providers are re-evaluated after a failure, allowing return to a primary whose
cooldown expired while the backup was responding. This state is a bounded
two-provider in-memory availability cache, not an account usage counter or a
Firestore operation.

Streaming failover sends `reset`, clears the old preview and sentence-guard state,
then checks the backup's output independently. The frontend never concatenates
two models' answers. The existing final output checks and atomic durable save
still run once for the resulting answer, and feedback/audio wait for completion.
Cancellation at the switching boundary prevents the backup call. The first-token
metric retains its first observation rather than summing two attempts.

Safety refusals and non-quota errors do not trigger switching. If both services
are cooling or both hit quotas, the operation ends with generic HTTP 503 / SSE
availability failure, without raw quota/exhaustion descriptions. It cannot
promise an answer while both services are unavailable. Switching has no deliberate
wait, but detecting the first failure and generating the backup answer still take
network/model time.

The versioned notice now names both services and explains that the same message
and permitted context may be sent to both when switching. Existing single-provider
consent does not authorize fallback; users must accept `2026-11-04.dual.1` once.
Subsequent switches do not change that notice. Prior feedback-sharing permission
remains valid because those terms are unchanged. Both providers' processing
confirmations gate health-note availability, and production validates both
providers' keys/models and confirmations before startup.

### Validation

`npm run check` passed **1,473 backend tests**, **282 UI tests**, **seven audio
tests**, both linters and the production build. A subsequent focused run passed
**21 HTTP-security tests**, including the added regression that first-token
measurements are not added together after a provider switch. Tests exercise both
directions, successful-primary short circuit, cooldown expiry, concurrent requests,
retry metadata, both-limited failure, stream reset, cancellation, refusals,
configuration/consent gates, client ownership/cleanup, final answer replacement
and a single durable save. The UI verifies removal of the previous provider's
preview while retaining the same question and request.

Two additional probes simulated the primary's HTTP 429 and called the actual
configured backup with a synthetic non-personal babbling question. No real quota
was intentionally exhausted, no account/database/profile data was used, and no
answer text or credentials were stored in the probe artifact.

| Simulated limited primary | Real backup | First backup delta | Complete generation |
| --- | --- | ---: | ---: |
| Groq | Gemini | 3,432.3 ms | 3,829.7 ms |
| Gemini | Groq | 1,602.7 ms | 1,843.1 ms |

Both returned successfully, with no provider refusal or output-guard block. These
are generation-only observations, excluding application authentication, data
reads and saving; they establish usable backup keys/models and streaming, not
instant or guaranteed full-application latency. Local startup configuration
validates and the app's proxied backend health returns HTTP 200.

Evidence:
[full verification](artifacts/performance/provider-failover-check.txt),
[live backup probes](artifacts/performance/provider-failover-live-probe.json).
Primary provider references:
[Groq rate limits and Retry-After](https://console.groq.com/docs/rate-limits),
[Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
