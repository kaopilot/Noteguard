# Noteguard rule catalog (ruleset v1, registry v1)

Owner: B1. Code: `noteguard/engine/` (one pure function per rule in `noteguard/engine/rules/`).
Every rule is deterministic, versioned (`check_version` = `ruleset@v1;rule@<id>.<n>;registry@v1`) and
reads its terms only from `rulesets/registry_v1.json` through the `RulesetBundle` (L5). Thresholds are
**placeholders pending clinical governance** (OPEN-8). A rule enabled in a ruleset but not built here makes
`run_checks` raise `NotImplementedError`; it is never skipped silently.

Evidence levels in this file: "executed" = a named test applies the input and was mutation-checked in
session B1.1 (see `docs/handoffs/B1.md`); "inspected" = read in code, no test.

## Shared mechanics (all rules)

- **Scope.** A source is in scope iff `source_time <= cutoff`; its latest version with `version_time <= cutoff` is used. Order: `(source_time, received_at, source_version_id)`.
- **Statements.** Every assertion and evidence span is a statement span from `contracts/spans.py`, in code points of the original text. Matching runs on normalised text (lower case, unified dashes, collapsed whitespace, thousands separators removed) with an offset map back.
- **Negation / uncertainty (8.1).** A registry negation or uncertainty cue scopes forward over the rest of its clause (split on `,` `;`), at most 6 word tokens, never across `:`. A `?` not touching a following word makes its whole clause uncertain. Uncertain wording lowers certainty to `queried` and sets `review_required`; it never becomes a negative.
- **Carried forward (8.3).** A statement equal, after normalisation and synonym → term-key replacement, to a statement in an *earlier, different* source; or near-verbatim (difflib token ratio ≥ 0.9 with identical numbers, registry terms and negated terms). Carried text never suppresses a flag.
- **Changes.** Each fact is classified against the latest earlier fact on the same subject: `carried_forward`, `explicit_change` (L3: registry change cue, clinician or pharmacy source, strictly later `source_time`), `reworded` (same normalised facts), else `new`.
- **Identity and reruns (8.4, L1, L2).** `flag_id = ids.flag_id(rule_id, encounter_id, subject_key)`. Evidence items are matched across runs on (source, role, normalised facts of the cited statement): an amendment restating the same facts keeps the original citation and sets `source_changed_since_flag`. New evidence carries a new `evidence_revision`; cited items are never dropped. The engine only raises, supersedes or reopens; `contracts.states` decides targets. A human-resolved or dismissed flag reopens only for new evidence from a source not already cited; a resolve that names the correct entry makes the other side's statements inactive for that flag, so restating the winning side never reopens.
- **Owners (8.6).** Tier 1 and `responsible_clinician*` rules → the responsible clinician, else the attending (never unassigned). `source_note_owner` → the author of the statement the flag is about (the uploader for external documents). `single_source_owner_else_responsible` → that author if all evidence is from one source, else the responsible clinician. `affected_contributor_ids` = evidence authors (+ care-team pharmacists for `responsible_clinician_plus_pharmacy`) minus the owner. An existing flag keeps its owner (reassignment is a human action).

---

## CRIT-001 — Critical result without documented response

| Field | Value |
|---|---|
| Lens / tier | completeness / 1 (protected floor) |
| Registry terms | `analyte` terms with `critical_high` / `critical_low` (placeholders): potassium ≥ 6.0 or ≤ 2.5 mmol/L; sodium ≥ 160 or ≤ 120 mmol/L |
| Subject key | analyte key, e.g. `analyte:potassium` |
| Owner | responsible clinician (else attending); note author in `affected_contributor_ids` |
| Evidence | `claim` = the unacknowledged critical observation(s); on supersede also every `suppressor` |

**Raises when** an analyte value is at or beyond a critical threshold and no suppressor follows it. A value written as queried (`?6.5`) still counts and is marked `review_required`. A later response statement that repeats an earlier critical value of the same analyte ("K 6.4 reviewed") refers to that result and is not a new observation.

**Suppressed (8.5) only by** a statement with a live response cue (review, repeat, treatment, escalation, transfer) in the same clause as the **same analyte**, in a source with a **later** `source_time`, **not carried forward**. Not raised if suppressed at evaluation time; a flag already seen becomes `superseded` (still blocks closure until the responsible clinician resolves with a reason code).

**Fixtures:** goldens ENC-A1_1130 (raised; "Not yet reviewed" does not suppress), ENC-A1_1600 (not raised), ENC-A1_1600_rerun (superseded), ENC-C1_1000 (routes to attending). Tests: `test_critical_observation_routing` (earlier / carried / negated / other-analyte / later), `test_tier1_never_auto_closed`, edges `same_statement_response_is_not_later`, `queried_critical_value_still_raised`, `critical_low_threshold`. Executed.

**Known false positives:** a response written in the same statement or same note as the value ("K 6.5, Dr informed") does not count, because 8.5 requires a later source. **Known false negatives:** a value not directly after the analyte term ("potassium result today was 6.4"); units other than the registry unit are `review_required` and not treated as critical; responses that name no analyte ("reviewed by medical team") never suppress (conservative).

## ALG-001 — Conflicting allergy documentation

| Field | Value |
|---|---|
| Lens / tier | contradiction / 1 (protected floor) |
| Registry terms | `allergen`, `drug_class` terms; `allergy_denials`; `allergy_keyword` cues |
| Subject key | the named allergen's key, e.g. `allergen:penicillin` |
| Owner | responsible clinician (else attending); pharmacists and all evidence authors affected |
| Evidence | `claim` = denial side (all of them), `counter_claim` = named-allergy side (all of them) |

**Raises when** an all-drug denial (registry phrase, e.g. NKDA) against a drug-related allergen, an all-allergy denial against any allergen, or a specific denial of a related substance ("denies penicillin allergy") coexists in scope with a named allergy. An allergen must sit within 3 tokens of an allergy keyword in the same clause. A queried allergy ("?penicillin allergy") counts as the named side (conservative; a clinician must decide). One flag per allergen, however many repeats (L1).

**Not raised:** denial alone; an unrecognised or queried denial ("allergies: nil?") is `review_required`, never NKDA, and is not used. Never resolved by source priority; only human adjudication (L2).

**Fixtures:** all ENC-A1 goldens, ENC-B1 (NKDA alone, no flag). Tests: `test_cross_note_conflicts`, `test_conflict_fanout_one_flag` (3 × 2 and 2 × 2 shapes), `test_adjudication_converges` (restate → no reopen; new denial → reopen), `test_cited_source_edited_side_by_side`, edges. Executed.

**Known limits:** "allergy check done before penicillin given" style sentences can read as a penicillin allergy (proximity rule); allergens absent from the registry are not detected; an unrecognised denial has no rule that surfaces it (it is recorded as a `review_required` assertion only).

## DOSE-001 — Dose differs between sources

| Field | Value |
|---|---|
| Lens / tier | consistency / 2 (protected floor) |
| Registry terms | `drug` terms, `dose_units`, `frequencies`, `change` cues |
| Subject key | drug key, e.g. `drug:amlodipine` |
| Owner | responsible clinician; pharmacists affected |
| Evidence | `claim` = the first regimen in the comparison epoch, `counter_claim` = every differing regimen |

**Raises when** the same drug has a different dose, unit or frequency in at least two sources with no explicit change linking them. Doses are compared after unit canonicalisation (`0.5 g` = `500 mg`) and frequency normalisation (`BD` = `twice daily`); a missing frequency is "not stated", not different.

**Not raised:** identical regimen after normalisation; an explicit change (L3) starts a new comparison epoch, so "Metformin increased to 1 g BD" by a clinician or pharmacist, later in time, is recorded as `explicit_change`. The same words from a nurse, or at the same time, stay a conflict.

**Fixtures:** ENC-A1 goldens (amlodipine flagged; metformin not). Tests: `test_cross_note_conflicts` (5mg/5 mg, 0.5 g/500 mg, frequency variants), `test_change_not_contradiction`, `test_differencing`, edges `negation_stops_at_colon`, `change_language_by_nurse_stays_conflict`. Executed.

**Known limits:** "increased from 500 mg to 1 g" is not parsed as a regimen (both doses go to DOSE-002 review); non-registry frequency wording ("at night") compares as "not stated"; no maximum-dose screen.

## DOSE-002 — Dose not recognised by the checker

| Field | Value |
|---|---|
| Lens / tier | completeness / 3 (protected floor) |
| Registry terms | `dose_units`, `drug` terms |
| Subject key | `unparsed_dose@source:<source_id>:<first 16 hex of sha256(quote)>` (one flag per statement) |
| Owner | source-note owner |
| Evidence | `claim` = the statement |

**Raises when** any number + registry dose unit is not attached to a parsed regimen (L4 broad catch). Attached = drug term, then separators (`:` `(` `-` `=`), optional change cue or "to/at/of/dose", then the dose. Handles `5mg`, `5,000 mg`, `Metformin: 5000 mg`, `Metformin (5000 mg)`. A number followed by `/` (g/L) is a concentration, not a dose. **A dose the checker did not parse is never a pass.**

**Fixtures:** ENC-A1 must-not-flag (every dose parsed, "1 g BD" included). Tests: `test_unparsed_dose_never_passes`, edges. Executed.

**Known false positives:** doses of drugs not in the registry ("Insulin 6 units") and doses written before the drug name. That is intended: unknown → review.

## PEND-001 — Pending item without owner or timing

| Field | Value |
|---|---|
| Lens / tier | completeness / 2 |
| Registry terms | `test` and `analyte` terms; `pending`, `owner` (regex), `timing` (regex) cues |
| Subject key | test or analyte key, e.g. `test:blood_culture` |
| Owner | single source → its author; cross-source → responsible clinician |
| Evidence | `claim` = each pending statement still missing owner or timing |

**Raises when** a statement has a live pending cue (pending, awaiting, sent, to chase) and names a registry test or analyte, and an explicit owner (registry owner pattern, e.g. `dr <name>`, `ward team to`) **or** explicit timing (e.g. `by 18:00`, `tomorrow am`, `by end of shift`) is missing from both that statement and every later statement naming the same subject.

**Not raised:** both present (same or later linked statement); negated cue ("not sent").

**Fixtures:** ENC-A1 goldens (blood culture flagged; "Repeat K sent; Dr Lim to review result by 18:00" not). Tests: `test_pending_owner_and_time` (owner only, timing only, neither, both, linked later statement), edges. Executed.

**Known limits:** subject and cue are associated at statement level, so "ECG done, blood culture sent" would also mark the ECG pending (false positive); tests and referrals not in the registry ("bloods", "referral") are not detected; timing phrases outside the registry list are not recognised (flag stays, conservative).

## PDF-001 — Document text could not be fully read

| Field | Value |
|---|---|
| Lens / tier | completeness / 2 (protected floor) |
| Subject key | `source:<source_id>` |
| Owner | source-note owner (the uploader) |
| Evidence | one `extraction_gap` per page with no text layer (`start == end ==` page start, `page` set, quote `""`) |

**Raises when** an in-scope source's extraction status is not `complete` or `not_applicable`. Closed only by a human decision (manual review or OCR). While any such source is in scope, every absence answer is `incomplete_extraction` naming it (8.8).

**Fixtures:** ENC-A1_1600 and rerun. Test: `test_question_bubble_grounding` (downgrade half). Executed. The intake half (status detection) is B2's `test_pdf_extraction_boundary`.

## DIFF-001 — Possibly copied-forward statement

| Field | Value |
|---|---|
| Lens / tier | continuity / 3 |
| Registry terms | `status` terms; `analyte` terms with `deterioration_*` thresholds (SpO2 < 92 %, RR ≥ 25/min, placeholders) |
| Subject key | `status:<term>@source:<source_id of the repeating note>` |
| Owner | author of the repeating note |
| Evidence | `claim` = the repeat, `origin` = first appearance, `counter_claim` = deterioration statements in between |
| Question | rendered from the rule's `question_template`, e.g. *Is the 16:00 "Patient stable" statement current?* |

**Raises when** a reassuring status statement is carried forward from an earlier source and a deterioration marker appears in a source strictly between the origin and the repeat. A review question, never a verdict. Critical-value thresholds are not deterioration markers here (@k decision, 22 Sep).

**Not raised:** carried text with no contradicting marker in between.

**Fixtures:** ENC-A1_1600 and rerun; ENC-A1_1130 must-not-flag. Test: `test_differencing` (benign copy raises nothing), variant test. Executed.

## OWN-001 — No responsible clinician recorded

| Field | Value |
|---|---|
| Lens / tier | closure / 1 (protected floor) |
| Subject key | `encounter:responsible_clinician` |
| Owner | the attending (8.6) |
| Evidence | one `encounter_record` item naming `encounter.responsible_clinician_id` (no span, never a fake anchor) |

**Raises when** the encounter records no responsible clinician. Every other Tier 1 flag then routes to the attending.

**Fixtures:** ENC-C1_1000 (golden pending @k review). Test: `test_golden_engine[ENC-C1_1000]`. Executed.

## DET-001 — Reassurance recorded after a deterioration marker (stretch; built B1.2, DISABLED in v1)

| Field | Value |
|---|---|
| Lens / tier | continuity / 1 (protected floor) |
| Status | built in `rules/deterioration.py`; `enabled: false` in `rulesets/v1.json` until **CCR-02** (goldens) is approved by @k |
| Registry terms | `status` terms; `analyte` terms with `deterioration_*` thresholds (placeholders) |
| Subject key | the status term key, e.g. `status:stable` (one flag per reassurance kind) |
| Owner | responsible clinician (else attending); evidence authors affected |
| Evidence | `claim` = the reassurance(s), `counter_claim` = unreviewed marker statement(s); on supersede also `suppressor` |
| Question | rendered from the rule's `question_template` |

**Raises when** a live, non-queried reassuring or discharge-readiness statement sits in a source with a later `source_time` than a deterioration marker, and no clinician review of that marker intervenes. Unlike DIFF-001 the reassurance need not be copied.

**Answered only by** a statement in a clinician-authored source with a live response cue in the same clause as the same analyte, not carried forward, at or after the marker's source and at or before the reassurance. A nurse's review or escalation, a review of another analyte, a review written after the reassurance, and a later normal value do not answer it (conservative; CCR-02 questions 1 and 3).

**Fixtures:** none in v1 (disabled). Tests: `tests/engine/test_det_001.py` (9 cases + shape/supersede + proposed-golden cross-check), run with DET enabled in an in-memory bundle only. Executed; 6 mutations, all caught.

**Known false positives:** a clinician's review written in general terms ("obs reviewed") names no analyte and does not count; a recovered observation does not clear it. The ENC-A1 16:00 statement would carry both DET-001 (Tier 1) and DIFF-001 (Tier 3) (CCR-02 question 2).

## Disabled in v1 and not built

`LAT-001` (laterality), `META-001` (metadata) and `NEXT-001` (no next step) are disabled in `rulesets/v1.json` and **not built**; enabling one makes `run_checks` raise `NotImplementedError`.
