# Golden fixtures (B0-owned; frozen at CP0)

`declarations.py` is the hand-written source of truth, written from the rule catalog (build context 8.2, 8.5, 8.6, 8.8, 8.9, 14.1). `materialize.py` turns it into the `*.json` files and `REVIEW_SHEET.md`; it resolves quotes to offsets, computes ids, validates against the contract and cross-checks the declarations, but makes no rule decision. Never edit the JSON by hand: `tests/contract/test_golden_fixtures.py` fails if it differs from a fresh materialisation. After CP0 only a CCR changes `declarations.py`.

| Scenario | Input | Why it exists |
|---|---|---|
| `ENC-A1_1130` | ENC-A1, cutoff 11:30 SGT, no prior flags | CRIT-001 raised (negated "Not yet reviewed" does not suppress); ALG, DOSE, PEND; absence answers over a fully readable scope |
| `ENC-A1_1600` | ENC-A1, cutoff 16:00, no prior flags | CRIT-001 **not raised** (suppressed at evaluation time); metformin change is not a conflict; PDF-001; DIFF-001; absence answers downgrade to `incomplete_extraction` |
| `ENC-A1_1600_rerun` | ENC-A1, cutoff 16:00, `prior_flags` = the 11:30 golden flags | The live path: CRIT-001 **superseded** (still blocks closure); ALG/DOSE keep their v1 citation and mark `source_changed_since_flag` |
| `ENC-B1_1600` | ENC-B1, cutoff 16:00 | Other care team; benign; no flags (access-control tests use it) |

`evaluated_at` is cutoff + 1 minute; `run_id` is fixed per scenario (see the JSON). Tests pass both into `run_checks`.

## What is compared, and how

Exact **set** equality, never "contains" (an over-flagging engine must fail). Helpers: `tests/support/golden.py`.

- **Run:** every `CheckRun` field.
- **Flags:** `flag_id, rule_id, tier, category, lens, title, subject_key, owner_staff_id, affected_contributor_ids (set), state, revision, evidence_revision, source_changed_since_flag, new_evidence_since_decision, ready_for_clinician, check_version, created_at, first_run_id, last_run_id`, whether `question` is set, and the evidence **set** of `(note_version_id, start, end, page, quote, quote_sha256, role_in_flag, evidence_revision)`.
- **Bubbles:** `bubble_id, question_template_id, subject_key, status, flag_id, rank, cutoff`, evidence set as above, and `absence` (`status, registry_version, cutoff`, `terms_searched` as a set, `sources_searched` as a set). Order must be `(rank, subject_key)`.
- **Summary:** `cutoff, generated_at, ruleset_version, registry_version, closure_status, human_review_statement`, the timeline as an ordered list, and claims as a set of `(template, params, evidence set)`.
- **Changes:** each `required_changes` entry must be present (resolved through `result.assertions` spans). Changes are the one "contains" comparison because every other assertion is `new`; flags stay exact.
- **Not compared, but linted** (`contracts.forbidden_phrases`) and required non-empty: `reason`, `question`, `uncertainty_note`, claim `text`. The hand-written text shows the intended register; B1 renders its own from `rulesets/v1.json`.
- `must_not_flag` is redundant with exact equality on purpose: it names the clinically important negatives so a failure message says which one broke.

## Conventions the goldens depend on (B1 must follow; change only by CCR)

1. **Spans:** every assertion and non-gap evidence span is a statement span from `noteguard/contracts/spans.py`. Offsets are code points into the original extraction. Extraction gaps: `start == end ==` page start, `page` set, `quote ""`.
2. **Scope:** a source is in scope iff `source_time <= cutoff`; its latest version with `version_time <= cutoff` is used. An amendment keeps its source's `source_time` (the medrec v2 still sits at 10:30).
3. **Subject keys:** registry key of the subject (`analyte:potassium`, `allergen:penicillin`, `drug:amlodipine`, `test:blood_culture`); `source:<source_id>` for PDF-001; `status:stable@source:<source_id of the repeating note>` for DIFF-001; `unparsed_dose@source:<source_id>:<first 16 hex of sha256(quote)>` for DOSE-002 (one flag per unparsed statement).
4. **Evidence roles:** `claim` = earlier side of a conflict or the statement the flag is about (ALG-001: `claim` = the denial side, `counter_claim` = the named-allergy side, whatever their order); `counter_claim` = later side; `origin` = first appearance of carried text; `suppressor` = documented response; `trigger` = what triggered a bubble; `extraction_gap` = unread page. In `ChangeView`: `from_evidence` role `origin`, `to_evidence` role `claim`.
5. **Owners:** Tier 1 and cross-source → responsible clinician; single-source → source-note owner (the uploader for external documents). `affected_contributor_ids` = authors of evidence sources, plus care-team pharmacists for `responsible_clinician_plus_pharmacy` rules, minus the owner.
6. **Suppression evidence:** every later, non-carried-forward, non-negated response statement naming the same analyte is a suppressor (both 15:30 statements).
7. **Existing flags on rerun:** keep citing the version they cited while the normalised facts still hold; a newer in-scope version of a cited source sets `source_changed_since_flag` and bumps `revision` (not `evidence_revision`). A change in the evidence set bumps both; new evidence items carry the new `evidence_revision`.
8. **Bubbles:** flag-rule bubbles only for unresolved flags; critical-observation bubbles for every critical analyte in scope, linked to that analyte's CRIT-001 flag if one exists in any state. Conflict and human-review bubbles carry the flag's evidence. `documented` bubbles carry the trigger plus every matching statement other than the trigger itself (role `suppressor`; for `q_crit_response` a matching statement is exactly one that would suppress CRIT-001 under Section 8.5, so earlier, carried-forward and negated lines never count); if the trigger statement itself answers the question, the trigger alone. `incomplete_extraction` bubbles carry the trigger plus one `extraction_gap` per unread in-scope source. `sources_searched` lists every in-scope version. `{subject_label}` is the term's first synonym.
9. **Summary:** one `open_priority` per unresolved Tier 1/2 flag (`states.is_unresolved`), one `decision_record` per decision, one `top_question` per first-three non-`documented` bubbles. Glance top bubbles = the same three.
