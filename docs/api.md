# API overview

[Documentation home](../README.md#documentation). Commands run from the repository root.

Protected endpoints require `Authorization: Bearer <Firebase ID token>` and verified
email. TOTP is required when enrolled or enforced by policy. Backend routes are also mounted under
`/api/v1`. See the generated API documentation for request/response schemas.

| Method | Route | Purpose |
|---|---|---|
| GET / POST | `/admin/feedback/improvements` | List or create the signed-in administrator's own fictional improvement cases; administrator role and MFA required |
| PUT / DELETE | `/admin/feedback/improvements/{id}` | Update or delete an owned case with its expected version; stale writes are rejected |
| GET | `/health/live` | Public liveness check |
| GET | `/health/ready` | Public readiness check. A known reference-service problem reports `degraded` while the app continues to serve requests. |
| GET | `/me` | Verify account access |
| GET | `/me/startup` | Verify access once and return the current consent notice and owned profiles for chat startup; administrators receive no caregiver data |
| GET | `/me/security` | Read MFA status and policy for the current verified account |
| POST | `/me/security/mfa/disable` | Disable optional MFA after a recent full sign-in |
| GET | `/children` | List the authenticated user's profiles |
| POST | `/children` | Create a profile with name, date_of_birth, optional milestones and private health notes |
| PATCH | `/children/{child_id}` | Update an owned profile |
| POST | `/speech/transcribe` | Transcribe raw WAV audio |
| POST | `/conversations` | Create a conversation for an owned child profile |
| GET | `/conversations?child_id=...` | List a child's conversations, newest first |
| GET | `/conversations/{conversation_id}` | Read a page of conversation messages |
| DELETE | `/conversations/{conversation_id}` | Delete a conversation and its messages |
| POST | `/coach` | Submit child_id, question, optional routine and conversation_id |
| POST | `/coach/{interaction_id}/feedback` | Rate an interaction or a conversation answer |

Speech requests accept mono PCM16 WAV at 16 kHz, up to 30 seconds, with a
964096-byte body limit. One transcription runs at a time per server process;
concurrent requests receive HTTP 429. The response includes `text`,
`audio_seconds`, and `processing_seconds`.

Coaching responses include `interaction_id`, `answer`, `citations`,
`child_age_months`, and `processing_seconds`. Playback is handled in the browser.

When `conversation_id` is supplied, `/coach` verifies that the conversation belongs
to the authenticated account and selected child. It saves the submitted message
and checked response together, then returns `conversation_id` and `message_id`;
`interaction_id` is null. Without a conversation ID, the existing interaction
storage and feedback contract remain available. New conversation messages are not
duplicated in the interactions collection.

For conversation feedback, put the assistant's `message_id` in the existing
feedback route and include `conversation_id` with either `helpful` or an integer
`rating` from 1 to 5, plus optional `reasons` and `comment` in the JSON body.
Feedback is stored on that assistant message. Historical boolean ratings are not
converted to numeric scores. Helpfulness ratings do not establish clinical accuracy
and do not automatically train a model.

History reads accept a bounded `limit` and optional `before` document ID. For older
conversation pages, use the last returned conversation ID; for older message
pages, use the first returned message ID. Message pages are returned in reading
order. The interface can open saved conversations and display messages, sources,
audio controls, and feedback. Its composer uses one editable field for typed text
and speech transcription beneath the scrolling message thread. For conversation
requests, the backend loads at most eight recent messages and selects up to four
complete answered exchanges within a 4,000-character budget. History helps
interpret follow-ups but is not reference evidence. Safety responses and
unsuccessful answers form a boundary: earlier turns are not carried past them.
Legacy interactions remain unchanged and are not yet included in the conversation
list.

Explicit short follow-ups such as "What else can I try?" can include the recent
caregiver topic in reference search. The Groq path can make a short, separate
request to interpret the caregiver's intent and the child's age. The server
validates that result and falls back to its conversation and age rules if the
result is unavailable or unusable. If a follow-up has no usable topic, the system
can ask for clarification. Context comes from the selected conversation.
For requests for more ideas, the generation instructions distinguish new actions
from reworded or rearranged earlier advice. When references offer no further ideas,
the answer can use cautious general information without attributing it to the
references. Requests for explanation may clarify a previous suggestion
without presenting it as new advice. These are prompt-level controls and require
live response evaluation; automated prompt tests do not establish semantic novelty.
