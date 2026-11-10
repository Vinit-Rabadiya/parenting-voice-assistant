# Input and output safety

[Documentation home](../README.md#documentation).

## Coaching output guardrails

After generation, `response_safety.py` checks common dose expressions, known
medication-instruction and diagnostic patterns, explicit conflicting age claims,
numeric citation bounds, model-generated links and source-record provenance.
Source cards must match the evidence records supplied to generation, including
their metadata. A blocked response is replaced before database storage and API
delivery. The frontend distinguishes `safety_blocked` from `no_evidence` and audio
playback reads only the returned replacement. Safety logs contain random request
identifiers, outcomes and reason codes, not conversation text.

These are limited deterministic guardrails, not comprehensive medical detection,
semantic grounding verification or expert clinical validation. The dose rule is
deliberately conservative and may block benign numerical references. Directly
negated medication instructions are exempted, but complex wording and unlisted
drugs or conditions can be missed. A passing check does not mean every claim is
supported by a source or that the answer is safe. Input danger-sign routing is
described separately below; broader scope classification remains outstanding. No additional model request
or change to the generation prompt is introduced.

The evaluation capture script applies the same checks. New records distinguish
`safety_blocked` outcomes and retain reason codes rather than the blocked generated
text. Earlier evaluation records remain unchanged; compare runs by code revision.

## Input danger-sign routing

Before retrieval or generation, an offline English-input gate returns a fixed
English/Kiswahili message for unsupported or uncertain text. Recognized urgent
English reports retain their fixed referral even in mixed-language messages.
The gate uses the pinned Lingua detector, sentence checks and selected Kiswahili
markers; it sends no text to another service. Edited transcripts pass through the
same coaching gate as typed messages. Refusals are saved with
`response_kind: unsupported_language` and excluded from later model context.
Short English acknowledgements, age replies and selected vaccine abbreviations
are supported explicitly. Language identification can still miss code-switching
or reject English wording; this does not add Kiswahili coaching or clinical triage.
See the [language development evaluation](../eval/README.md#english-only-language-boundary).

`input_safety.py` checks English input after authenticated profile lookup and
before retrieval/generation. Recognized reports of breathing difficulty, inability
to feed, convulsions, unresponsiveness, dehydration, choking, injury and fever in
profiles under three completed calendar months return a fixed urgent-care referral.
The response uses `status: escalated` and `safety: escalate`; ordinary responses use
`safety: not_flagged`, which is not a medical safety clearance. Recognized reports
for aged-out managed profiles still receive the referral instead of only an age error.

Referral sources are predefined, not generated or retrieved by similarity. The
Kenya handbook's danger-sign passage supports its listed categories; WHO emergency
guidance and NHS accident guidance cover additional categories. Web references have
`pdf_page: null` rather than fabricated page numbers. Input safety logs contain reason
codes and random request identifiers, not symptom text. A failed interaction write
does not suppress the referral: `interaction_id` is then null and feedback is hidden.
Authentication and profile lookup remain required; this is not an emergency service.

These are conservative keyword/pattern rules with narrow negation and prevention
handling, not a validated clinical triage tool. They require explicit child/pronoun
context and can miss implicit subjects, spelling errors, other languages and
unfamiliar symptoms. Explicit Celsius readings of 38C or above are routed for
profiles under three completed months. Unitless and Fahrenheit readings, other
age-specific numeric thresholds and complex symptom descriptions are not covered
by that numeric rule. Historical or hypothetical readings can cause false alarms.
Fever routing uses the resolved profile, explicit-message or clarified conversation
age, with a further check when context resolves a younger age. The
initial tests include 30 danger examples and 30 benign look-alikes, plus integration
checks; these are development examples, not an independently validated benchmark.
The fixed development evaluation is implemented in
[the safety workstream](../eval/README.md); independent professional validation
remains outstanding.

Sources:

- [Kenya Ministry of Health handbook, PDF page 45](https://www.health.go.ke/sites/default/files/2023-05/Mother%20Child%20Health%20Handbook%20MOH-FOR%20PRINT.pdf)
- [WHO paediatric emergency triage overview](https://www.who.int/publications/i/item/9789241510219)
- [NHS child accidents guidance](https://www.nhs.uk/baby/first-aid-and-safety/first-aid/what-to-do-if-your-child-has-an-accident/)
