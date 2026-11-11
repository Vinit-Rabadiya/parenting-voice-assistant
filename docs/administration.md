# Feedback administration

[Documentation home](../README.md#documentation). Commands run from the repository root.

Administrator accounts open a dedicated **Administrator dashboard** after sign-in,
with rating and reason panels loaded directly on the page. **Refresh feedback**
reloads the report. Exact category counts appear from the first eligible response;
an empty state appears when there is no eligible feedback.
They do not enter the caregiver workspace
or create child profiles, start coaching conversations or record questions.
Caregiver accounts keep the existing chat workflow. Backend authorization requires the
boolean `feedback_summary_admin` custom claim in a verified Firebase token, in
addition to verified email and completed authenticator sign-in. The permission
must also still be present on the current provider account record; an older
token alone cannot retain a removed administrator role. MFA is mandatory for
these accounts and cannot be disabled through account settings.
There is no endpoint for granting permission or opening other accounts' chats.

There is no separate administrator password or public administrator registration.
Use a dedicated account, register or sign in through the normal page, verify its
email and enable MFA in My Account. A trusted system operator then grants the
role using the command below. After signing out and back in with the authenticator,
the dashboard opens automatically and loads a read-only view of grouped
helpfulness ratings and reason categories, used to identify improvements for
separate investigation and evaluation. It does not edit models, manage other
accounts or display private conversations and child profiles.

The `/me` response supplies the server-checked account role used for navigation.
Caregiver feature APIs also reject administrator sessions; hiding controls alone
does not enforce the separation. **My Account → Settings** remains available for
the administrator's own security and account deletion. Caregiver consent and usage
controls are hidden there. Existing personal data from before a role change is
retained until the account owner deletes it; changing role does not delete records.

The overview contains counts for numeric ratings, optional reason categories and
separate historical Helpful/Not helpful feedback. **Written feedback** shows up to
50 of the most recent shared comments, with their ratings and selected reasons.
It does not attach questions, answers, transcripts, names, birth dates, account IDs,
individual timestamps or conversation links. Comments contain the text supplied
by the caregiver; both the notice and comment field explain administrator access
and ask caregivers to avoid names and private details. There are no account filters,
exports, totals, averages or conversation drill-down. Each answer's saved feedback contributes once,
including multiple answers rated by the same caregiver. Editing feedback replaces
that answer's previous contribution. There is no minimum number of caregivers;
counts include categories with one response. A response may select more than one
reason, so reason counts should not be added together as a response total.

Notice version `2026-10-26.2` explains this use. A contribution is eligible only
when its account accepted the current notice and its recorded time is at or after
acceptance. Old feedback is not repurposed automatically. An intentional edit after
acceptance is a new contribution. Numeric ratings are never inferred from old
boolean ratings. Earlier notices did not authorize written-comment review, so
accepting the new notice does not expose comments recorded before acceptance.
The former per-message `review_status` field is no longer created or
returned; historical fields need no migration and do not grant review access.

The service projects only feedback rating, helpfulness, reason, comment and recorded-time
fields, plus message role. It recomputes from retained source records without
creating a separate feedback copy or training dataset. After an edit or completed deletion, the
next summary reflects the remaining eligible contributions. It scans at most
10,000 documents per collection group and 500 accounts, with a ten-second
processing budget and bounded individual database calls. Failure, timeout or a
limit produces an unavailable response, never partial counts or invented zeroes.
At larger scale, use a separately reviewed aggregate pipeline rather than raising
limits silently. No summary scan runs during coaching, so this adds no model calls
or reference retrieval to caregiver requests.

### Grant or revoke access

Run these commands only on a trusted server with the existing Firebase Admin
credentials. Replace `ACCOUNT_UID` with the intended account's Firebase UID.
Preview does not connect to Firebase or change an account:

Find the intended account's UID under **Firebase Console → Authentication → Users**.
Replace `ACCOUNT_UID` below with that UID; the example is not an account to create.

```powershell
.\venv\Scripts\python.exe -m scripts.set_feedback_admin --uid ACCOUNT_UID --grant
.\venv\Scripts\python.exe -m scripts.set_feedback_admin --uid ACCOUNT_UID --grant --apply
```

Revoke access with:

```powershell
.\venv\Scripts\python.exe -m scripts.set_feedback_admin --uid ACCOUNT_UID --revoke --apply
```

The command preserves unrelated custom claims and revokes existing sign-in
sessions. Sign in again after a successful change. If session revocation fails,
retry the command; do not assume revocation is complete. No real account is
promoted by setup or automated tests. Application permission does not grant cloud
console access; protect production service credentials and cloud IAM separately.
See [Firebase custom claims](https://firebase.google.com/docs/auth/admin/custom-claims)
and [session revocation](https://firebase.google.com/docs/auth/admin/manage-sessions).

### Lost authenticator recovery

The feedback-overview permission does not grant account-recovery powers. Recovery
is a separate trusted operator action, after independently verifying the account
owner's identity. The existing command previews without changing an account:

```powershell
.\venv\Scripts\python.exe -m scripts.reset_account_mfa --uid ACCOUNT_UID
.\venv\Scripts\python.exe -m scripts.reset_account_mfa --uid ACCOUNT_UID --apply --identity-verified
```

Applying recovery removes enrolled authenticators and invalidates existing sessions.
Mandatory MFA policy, including administrator policy, is retained. The recovered
administrator must enroll and complete MFA again before opening grouped feedback.

### Improvement workflow without private chats

1. Review rating and reason counts for improvement signals; a low rating alone
   does not establish an incorrect answer.
2. Open an improvement issue using only the category and a separately written
   test question. Shared comments may inform the investigation, but do not copy
   a caregiver's question, answer, private details or comment into a public issue.
3. Reproduce the concern with the existing evaluation tools. Record the test
   case, original sources, corpus fingerprint, actual model/prompt configuration
   and evaluation split. Keep tuning separate from held-out evaluation.
4. Review a source, retrieval or prompt correction and compare the same
   development example before and after. Do not describe source checks or automated
   evaluation as professional validation; that review has not been obtained.
5. Link the correction and evaluation evidence in the improvement issue, then
   close that issue when its acceptance criteria are met. Do not mark an
   individual private conversation reviewed or train automatically from ratings.

Administrator review identifies problems to reproduce with separate evaluation
cases. Compare a correction or candidate model on the same cases before adoption.
This workflow does not fine-tune Gemini or the speech model, and written comments
alone are not reference transcripts or validated training examples.

A synthetic demonstration is documented in
[the coaching evaluation review](../data/evaluation/coaching-quality-review.md#aggregate-feedback-improvement-example).
