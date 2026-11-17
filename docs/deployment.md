# Deployment modes and hosting

[Documentation home](../README.md#documentation). Commands run from the repository root.

## Deployment modes

`APP_ENV=production` enables configuration checks; it does not certify that a
deployment is suitable for real caregiver data. The operating guidance below
treats the demonstration as **fictional test profiles and non-personal example
messages only** until a reviewed pilot configuration is recorded. The running
container's flags, provider accounts, billing and deployed commit have not been
verified during this documentation update.

| Mode | Permitted use under this project guidance | Provider confirmations |
| --- | --- | --- |
| Local development | Fictional profiles and messages; private credentials remain outside source control | `APP_ENV=development` does not enforce production confirmation checks; health-note sharing still has its own gate |
| Hosted demonstration | Controlled testing with fictional child profiles, notes, current questions and earlier chat context | For each enabled provider, use its non-personal-testing confirmation only after checking all supplied content |
| Real-caregiver pilot | Only after reviewing the actual provider account, processing arrangements, notices, retention and access controls | Confirm Gemini paid-service processing or Groq data terms for every enabled provider; do not use a non-personal-test assertion for real personal data |

The demo still uses Firebase for tester sign-in. The non-personal confirmation
applies to model-request content; it does not anonymize an email address, account,
profile or message. Authentication, HTTPS and a consent checkbox do not stop a
tester typing real details. Keep the demo controlled and explain its test-data
restriction before use. Documentation alone does not enforce that restriction.

### Example model-processing confirmations

These snippets show confirmation flags only. Configure keys, models, exact hosts
and all other required settings separately. Set only the flags whose assertions
you have actually verified. All confirmation flags default to `false`.

Gemini non-personal demonstration:

```dotenv
COACHING_PROVIDER=gemini
COACHING_PROVIDER_FAILOVER=false
GEMINI_PAID_SERVICES_CONFIRMED=false
GEMINI_NONPERSONAL_TESTING_CONFIRMED=true
```

Gemini pilot after confirming the relevant project's paid-service arrangements:

```dotenv
COACHING_PROVIDER=gemini
COACHING_PROVIDER_FAILOVER=false
GEMINI_PAID_SERVICES_CONFIRMED=true
GEMINI_NONPERSONAL_TESTING_CONFIRMED=false
```

Groq pilot after checking its account terms and data controls:

```dotenv
COACHING_PROVIDER=groq
COACHING_PROVIDER_FAILOVER=false
GROQ_DATA_TERMS_CONFIRMED=true
GROQ_NONPERSONAL_TESTING_CONFIRMED=false
```

For a Groq demonstration, use `GROQ_NONPERSONAL_TESTING_CONFIRMED=true` only for
non-personal test requests and keep `GROQ_DATA_TERMS_CONFIRMED=false`. With
`COACHING_PROVIDER_FAILOVER=true`, both providers can receive the question and
permitted context. Review and confirm **both** providers independently; confirming
one does not authorize the other. Paid Gemini processing does not configure Groq.

The code reads operator confirmations. It does not inspect contracts, query
billing, enable paid services, anonymize content, configure provider retention or
restrict who can type personal details. A stored real question or health-tailored
answer can also enter later context; changing a flag does not sanitize history.

### Before moving from demo to pilot

1. Record the actual deployment revision, enabled providers, project/account,
   processing terms, data controls and review date. Verify the relevant billing
   configuration where the provider's terms depend on it. Do not treat the flags
   as evidence that this was checked.
2. Review which profile fields and health notes are necessary. Use health details
   only with explicit caregiver choice and the applicable provider gate; optional
   test-result notes are not necessary for a basic coaching demonstration.
3. Review the [data-flow and retention statement](privacy.md#retention-and-deletion)
   against actual Firestore, backup, log and provider settings. The application
   does not enforce an automatic expiry period for caregiver data.
4. Make the processing notice match the planned use. If its terms change, update
   its version and obtain renewed acceptance before that processing. Switching
   provider or enabling cross-provider failover already selects a different
   notice version; changing a billing/test confirmation alone does not.
5. Verify account isolation, deletion, runtime secrets, proxy/host settings and
   signed-in behavior on the target deployment. Preserve the explicit
   [evaluation limitations](evaluation.md); no clinical approval or Kenyan-speaker
   accuracy result is implied by deploying the application.

This is operator guidance, not a declaration of regulatory compliance or a claim
that a real-caregiver pilot is currently authorized.

## Provider data-processing requirements

Provider references were reviewed for this documentation on 10 November 2026.
Check the current terms and actual account configuration before a pilot:

- [Gemini API additional terms](https://ai.google.dev/gemini-api/terms) distinguish
  unpaid and paid processing. Unpaid services must not receive personal,
  confidential or sensitive content. For paid processing, verify the actual Cloud
  project/billing arrangement and applicable processing terms. Paid processing
  is not a blanket zero-retention promise.
- [GroqCloud data handling](https://console.groq.com/docs/your-data) distinguishes
  inference content, usage metadata, retained features and reliability/abuse logs.
  Review the organization's Data Controls and retention options. This app does
  not enable zero-data-retention settings or verify them through the Groq API.
- Firebase/Firestore also process account and application data. Qdrant Cloud
  inference processes retrieval queries. Review those services' actual contracts,
  region, retention and access settings separately; model-provider confirmations
  do not cover the entire system. See [data flows](privacy.md#data-flows).

## Hosting and security

The API verifies Firebase sessions, verified email, account ownership and applicable
MFA policy. Private API responses use `Cache-Control: no-store`. Incoming JSON bodies
are limited to 64 KiB and other bodies to 1 MiB, with a 15-second upload deadline;
audio validation also enforces the existing 30-second recording limit. The upload
deadline does not limit model generation. Provider error descriptions are excluded
from application diagnostics.

Before public deployment:

- Serve the built frontend and API through HTTPS. Configure the hosting platform's
  security headers, request throttling, concurrency limits and trusted proxy settings.
  Vite's development and preview servers are not production hosting.
- Keep backend API keys and Firebase Admin credentials in the host's secret store.
  Never include them in frontend variables, public files, source control or images.
- Retain Firestore rules that deny direct client access. The backend uses server
  credentials, so its IAM permissions must be limited separately.
- Restrict the public Firebase browser key to the Firebase APIs required by the app;
  keep generation-service keys private and separate. Add only the intended authentication domains.
- Enable repository secret scanning and push protection where available.
- Confirm the model provider's data-handling terms for the configured account and
  service tier before processing personal information. Gemini's unpaid-service terms
  prohibit submitting sensitive, confidential or personal information; see the
  [Gemini API terms](https://ai.google.dev/gemini-api/terms).
  For Groq, review [GroqCloud data handling](https://console.groq.com/docs/your-data),
  the account's Data Controls and applicable terms separately. Do not infer permission
  from Gemini settings or claim zero retention without checking the actual account.

Dependency audits and automated tests do not replace checking the deployed host,
cloud permissions and provider account configuration.

Container builds, Azure workflow operation and domain setup are covered in
[the hosting guide](hosting.md).

## Production configuration

Local development defaults to `APP_ENV=development`. Production startup requires
`APP_ENV=production`, an explicit comma-separated `ALLOWED_HOSTS` list of API host
names, and the selected provider's data-term or non-personal testing confirmation.
For Gemini these are `GEMINI_PAID_SERVICES_CONFIRMED` and
`GEMINI_NONPERSONAL_TESTING_CONFIRMED`; for Groq they are
`GROQ_DATA_TERMS_CONFIRMED` and `GROQ_NONPERSONAL_TESTING_CONFIRMED`.
Host names must not include a URL
scheme, port or wildcard. Production requests to an unrecognized host are rejected;
HTTP requests to an allowed host redirect to HTTPS.

Set the paid-services confirmation only after checking active Cloud Billing and the
applicable provider terms. Groq has its own data-term confirmation. These settings
record operator confirmations; they do not query billing or change provider data
handling. All confirmations default to false.

For hosted free-tier testing with general, non-personal example messages, keep
`GEMINI_PAID_SERVICES_CONFIRMED=false` and set
`GEMINI_NONPERSONAL_TESTING_CONFIRMED=true`. This records an operator confirmation
about model inputs; it does not remove identifying information or verify content.
Publicly available text still requires checking for personal or sensitive details.
The same restriction applies to follow-ups and conversation context. Normal sign-in,
HTTPS and host restrictions remain enabled. Review the configuration before changing
how the hosted application is used.

When HTTPS terminates at a reverse proxy, configure Uvicorn to trust forwarded
headers only from that proxy. Incorrect proxy settings can cause redirect loops.
The public hostname and proxy addresses depend on the selected hosting platform.

On Google-managed hosting, `FIREBASE_USE_ADC=true` uses the attached service account.
Unset `FIREBASE_ADMIN_KEY_PATH` in that mode. Other hosts can mount a private key
from a secret store using the existing key-path setting. Do not grant the runtime
service account Owner or Editor merely to inspect cloud settings: use an operator
account for administration. Runtime access needs Firestore data permissions and
the Firebase Authentication permissions used for reading accounts, updating MFA
and deleting accounts; review these separately from operator privileges.

The checked-in `firestore.rules` denies direct client access, and `firebase.json`
maps that rules file and the existing indexes. The backend remains responsible
for account isolation because server credentials bypass Firestore rules. Changes
to these local files are not published automatically. `.dockerignore` excludes
environment files, common private-key files, local credentials and logs from the
container build context.

CI includes a Gitleaks scan of new commits with redacted findings. It uses a pinned
release with checksum verification, does not post comments or upload reports,
and needs no secret-scanning subscription. This detects leaked secrets after a
push; it does not replace before-push protection or the cloud credential review.

## Application abuse and browser protections

Production uses short-lived, in-memory burst checks: eight processing starts may
arrive together, with one allowance replenished every three seconds. There is no
hourly or daily caregiver usage quota. Each process permits four simultaneous
processing requests, at most two per account, and one speech inference. Rejected
requests receive HTTP 429 and a short Retry-After value; accepted requests are not
queued by these controls. Sign-in, data deletion and the public emergency contacts
remain outside the processing quota. Actual model workers retain their capacity
until they finish, including after a browser disconnects.

Authenticated reads have a separate, more generous burst allowance of 32,
replenished once per second, to protect database reads without using up processing
allowances. Development keeps concurrency protection but disables burst throttling.

Uploads have bounded parallel body reads, size and upload-time checks. The
container also limits concurrent HTTP connections. These are per-process controls;
larger deployments should add shared ingress protection against distributed abuse.

The browser policy permits the configured Firebase project's sign-in origins.
When Firebase uses a custom authentication domain, add its exact HTTPS origin to
`CSP_AUTH_ORIGINS` before deployment. Test Google sign-in, authenticator setup and
recording on the hosted domain after changing authentication origins.

Reference destinations must appear in the checked-in source manifests copied into
the image. Use a collection-scoped, read-only Qdrant key at runtime, and reserve
write credentials for indexing. An allowed citation URL does not prove that the
retrieved excerpt is authentic or that a generated answer is medically correct.
Review provider data terms before using real personal data: testing confirmation
flags are operator assertions, not anonymization. Rotate previously exposed private
keys in their provider consoles; changing application code cannot revoke them.
