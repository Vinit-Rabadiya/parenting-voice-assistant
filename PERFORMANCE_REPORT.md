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
