# Coaching requests and streaming

[Documentation home](../README.md#documentation). Commands run from the repository root.

Application hourly/daily quotas and the My Account Usage panel have been removed.
Coaching and child-profile creation no longer read, reserve or update usage
counters. `/me/usage` is no longer an API route, and the old `COACH_*_LIMIT`,
`CHILD_CREATE_*_LIMIT` and `USAGE_LIMIT_BACKEND` settings are no longer used.
External providers can still return their own HTTP 429 responses; the app reports
these without automatically resending requests.

The chat requests `POST /coach` with `Accept: text/event-stream`. JSON callers
continue receiving the existing complete `CoachingResponse`. Both variants
require the same authenticated caregiver, current consent and ownership checks.
Current consent, the owned profile and optional conversation header are loaded in
one account-scoped Firestore BatchGet; only that request reuses the snapshots.
Ordinary follow-ups then query the latest bounded message page without reading
the parent again. Saving still rechecks current ownership and deletion flags.
Batching reduces network calls, not the number of billable documents read.

Streaming uses real Groq/Qwen or Gemini provider deltas. The backend releases
complete sentence prefixes after the existing output checks. Care-specific
validation that depends on a whole answer holds that answer until its complete
review. These pattern checks remain limited safeguards, not clinical validation.
A later provider refusal or full-answer replacement can replace an earlier
checked prefix. The browser renders arriving text directly, without a simulated
word-reveal timer. Authentication, data reads and provider first-token latency
still happen before answer text is available.

SSE events are `status` (`preparing`, `writing`, `saving`), `delta` (append checked
text), `ready` (replace the preview with the fully reviewed answer), `done`
(final response with stored IDs and timing metadata), and `error`. An answer can
be visible while its durable save is in progress. Feedback and audio stay
disabled until `done`; an interrupted stream never confirms a partial answer as
saved. A failed or cancelled stream removes its preview. A save that already
started can still finish after the browser stops waiting, so reopen the
conversation before resending an uncertain request.

Streams have a bounded 16-event queue with backpressure, a 16,000-character
output bound, terminal provider-finish checks and a 45-second deadline checked
between provider chunks, with network timeouts bounding stalled reads.
Cancellation is checked on provider deltas and closes the upstream iterator;
a blocked network read can still take its configured timeout to return.
Single-provider model fallback is permitted only before any output delta.
Cross-provider failover can restart a stream using `reset`, which clears the old
preview and sentence guard before any backup text. SSE responses are private/no-store and request proxy buffering be
disabled. No raw token, question or answer is included in timing captures.

`Server-Timing` is sent with response headers, so it measures header availability
for a stream. The final `done.timings_ms` and the optional development capture
include later stages: `generation_first_token` measures time from the provider
stream request to its first delta; `first_answer` measures time from the incoming
request to the first checked text being queued; `total_ms` in a completed capture
measures through stream completion and saving. These are server measurements,
not browser paint timings. Capture records mark the stream outcome separately
from its already-sent HTTP status.
