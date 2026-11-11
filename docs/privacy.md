# Data handling and retention

[Documentation home](../README.md#documentation). Commands run from the repository root.

## Data flows

| Data | Application use and destination |
| --- | --- |
| Sign-in and account details | Firebase Authentication; backend access checks use Firebase Admin |
| Child name, birth date, milestones and optional health notes | Private per-account Firestore profile; age is calculated on the server |
| Recorded audio | Local application-host Whisper transcription; the app does not deliberately persist the recording or send audio to the generation provider |
| Submitted question and follow-up search context | Qdrant Cloud inference when retrieval is used; current messages and bounded context also go to the enabled generation provider(s) |
| Calculated age, routine, selected milestones and references | Generation-provider prompt; stored name and birth date are not automatically copied into that prompt |
| Enabled health notes | Generation only when the caregiver enables their use and every applicable provider permission gate passes; not added to Qdrant retrieval queries |
| Messages, replies, sources, timestamps and feedback | Private per-account Firestore history; permitted feedback ratings/reasons/comments can contribute to administrator reports |

Profile identifiers are not automatically included in prompts, but a caregiver can
type identifying information into a question, note or feedback comment. The
confirmation flags do not redact it. Provider failover can send permitted context
to both Gemini and Groq. The [deployment guide](deployment.md#deployment-modes)
explains test-data restrictions and the review required before a real-caregiver pilot.

## Retention and deletion

This is the current application behavior, not a new time-based retention policy.
There is **no implemented automatic expiry/TTL cleanup for caregiver records**.
Do not promise deletion after a fixed number of days without implementing and
verifying it. The documentation update does not change storage or delete data.

| Data | Current retention and removal behavior |
| --- | --- |
| Recorded audio in the running app | Processed for transcription; not deliberately saved by application code. No claim is made about host-level crash dumps or operator captures |
| Profiles, milestones and health notes | Kept in Firestore until edited/cleared or removed by child deletion, Delete my data or Delete my account |
| Chats, sources, timestamps and attached feedback | Kept until the conversation, child data or account data is deleted; legacy standalone interactions are removed by the relevant child/account-data cleanup |
| Current processing-consent record | Kept with the user data; Delete my data removes it, so new processing requires acceptance again |
| Firebase login account | Delete my data retains it; Delete my account additionally deletes the Firebase Authentication user |
| In-memory workspace and reference/security caches | Bounded process/browser caches, with their configured lifetimes and invalidation rules; not an expiry policy for stored Firestore data |
| Browser automatic-playback preference | Stored per account in that browser until changed or cleared; deleting data/account clears the app's preference in the current browser |
| Cloud logs, backups, provider-held records and exported copies | Governed by separate host/provider/operator settings; app deletion does not erase them or prove immediate backup removal |
| Offline speech-evaluation recordings, references and reports | Separate local files kept until manually removed under the evaluation plan; account/data deletion in the app does not remove them |

`DELETE /me/data` recursively deletes application records under `users/{uid}`
while preserving the login account. `DELETE /me` deletes application data first,
then the Firebase Authentication account. Both require a sign-in completed within
five minutes. Deletion failures return an error and can leave partial removal;
retry rather than treating a failed request as proof of completion.

Clearing health notes stops their future prompt use and invalidates relevant
context. It does not erase existing answer text. Delete the relevant conversation
to remove that saved text from application history. Similarly, application
deletion cannot recall a previously exported administrator report or provider log.

Before a pilot, record the actual Firestore backup/PITR configuration, hosting log
expiry, provider retention options, access permissions and responsibility for
deletion requests. These settings were not inspected during this documentation
update. If a timed retention policy is required, that is separate implementation
work; no duration is invented here.

## Consent and sensitive profile context

The current notice names the enabled generation provider(s), explains storage and
feedback sharing, and requires caregiver authority before new processing.
Acceptance is checked before transcription, profile mutations, coaching and
feedback. Read/delete/account controls remain available without new acceptance.

Optional allergy, condition, history, care-instruction and test-result notes can
contain sensitive information. Minimize what is collected; fictional notes are
sufficient for demonstrations. Notes are privately stored by default and enter a
prompt only with the caregiver's opt-in and the configured provider gate. That
gate accepts either reviewed data-term confirmation or non-personal-test
confirmation; the latter supports only fictional test notes. It does not
authorize processing real health information. A confirmation does not establish
compliance or replace a review of the intended pilot's processing arrangements.

Changing the text or scope of processing requires a matching notice and version
review. This documentation describes existing behavior and does not change the
in-app notice, its version or its acceptance records. Provider-specific operating
guidance is in [the deployment guide](deployment.md#provider-data-processing-requirements).

## Storage and profile behavior

Firebase manages sign-in credentials. FastAPI validates tokens on every protected
request and enforces verified email, ownership, MFA and security policy. Remote
caregiver account/revocation checks can be reused for the bounded interval
documented in [the authentication setup](setup.md); sensitive and administrator
operations always refresh them.

Profiles are stored under `users/{uid}/children/{id}`. New conversation messages,
references, timestamps, and feedback are stored under
`users/{uid}/conversations/{id}/messages/{id}`. Earlier standalone interactions
remain under `users/{uid}/interactions/{id}`.
Recorded audio is processed for transcription and is not deliberately persisted by
the application. Edited text is submitted only when **Get guidance** is selected.

Qdrant Cloud inference processes question text for retrieval; explicit follow-ups
can also include a recent caregiver message from the selected conversation.
The selected generation provider receives the question, current calculated age, routine, retrieved reference
passages, and bounded recent conversation context when available.
Saved additional milestones are passed as caregiver-reported context, without treating
the baseline milestone display as achieved abilities. The conversation privacy disclosure explains that application history
is retained until the conversation, child profile, or account is deleted.
This is not a claim about third-party
provider or backup retention. Account deletion is available in account settings.
Before new processing, the interface displays a versioned notice and requires
explicit acceptance and confirmation of caregiver authority. The backend records
`consent_version`, server-generated `consent_at`, and `caregiver_authority` on
`users/{uid}`. Existing accounts without a current record must also accept; no
consent is inferred from previously stored profiles.

Authenticated `GET /privacy/consent` returns the current notice and acceptance
status. `POST /privacy/consent` accepts only the current version with both explicit
confirmations. The backend checks consent before profile creation/updates, new
conversations, coaching, feedback, and transcription. A missing or outdated record
does not block existing-data reads, deletion, or account settings. The notice
offers a read-only history view without acceptance.

Child names and dates of birth are retained for profile identification and
age-aware guidance; profile photos are not collected. Consent withdrawal controls
and broader privacy requirements still need separate work;
this flow alone does not establish legal compliance. Use fictitious profiles for
evaluation. Change the notice version when its processing terms change so an old
acceptance cannot silently authorise new terms.

### Profile context in replies

Add or edit a profile's optional **Health and care details** for short allergy,
condition, history, clinician-instruction and test-result notes. Each field is limited
to 600 characters. Existing profiles work without migration. Clearing these fields
removes their contents from the profile; deleting the child or account uses the existing
recursive cleanup. These notes are not added to administrator feedback reports or logs.

The coaching endpoint reads the selected profile from the authenticated account on
each request. Saved additional milestones are included in the existing generation
call as unverified observations. Baseline milestone suggestions are not treated as
achievements. Profile names, dates of birth and health notes are not added to retrieval
queries. Explicit conversation age overrides do not inherit saved profile context.

Health notes are saved privately by default. Using them in replies requires both the
profile's **Use health details to tailor replies** choice and either the reviewed
provider data-term confirmation or explicit non-personal testing confirmation. The latter
permits only non-personal test notes and does not enable billing or authorize personal
health information. The generation service rechecks this configuration before building
the prompt. Without either confirmation, notes remain available for private storage
and editing but are not included in model requests.

Health-tailored replies carry only a use marker and a random profile revision in
conversation metadata, rather than another copy of the notes. Changing or clearing
notes, disabling their use, or withdrawing provider permission stops old health-tailored
turns from being reused as model context. Saved chat text remains readable until its
conversation is deleted. Guidance must not diagnose, interpret test values, prescribe
treatment or override clinician instructions. Automated tests verify these data paths
and prompt rules, not clinical accuracy.

Within the same open signed-in session, account navigation preserves the chat
workspace, selected conversation, draft, and loaded consent state in memory.
Recording and spoken playback stop when leaving chat. Confirmed account access
is not rechecked merely on window focus. Reloading the app or changing accounts
revalidates access; backend authentication and consent checks still apply to each
protected request. Data deletion resets the retained workspace and consent state.

Account settings offer separate **Delete my data** and **Delete my account**
actions. Authenticated `DELETE /me/data` removes application data, including child
profiles, conversations, feedback, legacy interactions, and the consent record,
while retaining the login account. Consent must be accepted again before new
processing. `DELETE /me` also deletes the login account. Both actions require a
sign-in completed within the last five minutes and remain available without
consent. Deletion affects application storage, not third-party provider records
or backup copies.

Coaching requests have a 60-second browser wait limit and a **Stop waiting**
control in place of the Send arrow. Submitted messages appear immediately in the
thread and clear the input; failed or cancelled requests leave a local message
with an unconfirmed-answer status. Any new draft stays in the input. Cancellation
does not automatically retry.
It stops the browser waiting, not necessarily server processing: the answer may
still be saved. Reopen the conversation before deciding whether to send again.
Sources are collapsed by default and can be expanded for inspection.
