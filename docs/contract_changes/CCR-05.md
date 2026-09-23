# CCR-05 — Align the ENC-C1 OWN-001 golden `reason` with the ruleset template
Raised by: I1, session I1.1   Date: 24 Sep 2026
What changes (files, fields, values): `fixtures/expected/declarations.py`, the OWN-001 `reason` for ENC-C1_1000,
  becomes `rulesets/v1.json`'s OWN-001 `reason_template` verbatim; `make goldens` regenerates
  `fixtures/expected/ENC-C1_1000.json` and the review sheet. No contract, ruleset or registry change.
Why (the failing case or missing capability): I1's API-level golden run (real engine) shows the engine emitting the
  template, while B0's hand-written golden adds "on the care team" and names the attending. No test saw it: the
  engine-level comparison leaves `reason` out of FLAG_FIELDS, and B2's full-JSON API comparison ran on the stub,
  which serves the golden itself. @k ruled that the template is right (option (a)).
Lanes affected and what each must do:
  - Integrator (I1): edit declarations.py, `make goldens`, and land it in ONE commit with B4's refresh; then delete the
    CCR05 override in `tests/e2e/test_api_real_engine.py`.
  - B4: `labelled.corpus_sha256()` hashes the bytes of every golden JSON, so the report hash changes. Regenerate the
    committed `fixtures/labelled_eval/reports/EVAL_v1_vs_v1.json` and refresh `evaluation_report_sha256` in
    `rulesets/APPROVAL_v1.md` (metrics are expected to be unchanged: `reason` is not scored).
  - @k: re-sign APPROVAL_v1 on the refreshed report hash (the ruleset and registry hashes do not change).
  - B2, B3: none (no copy of the text in frontend/; B2's golden-through-API test serves the updated golden via the stub).
Golden fixture impact: one field of one flag in ENC-C1_1000. Attach the review-sheet diff at landing.
Status: approved (@k, 24 Sep 2026, chat I1.1, option (a)). NOT LANDED: landing waits for a B4 session and @k's re-sign-off.
  Meanwhile v1 stays approved on the current, consistent evidence (decisions/I1.md #18).
