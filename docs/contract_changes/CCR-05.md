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
Status: approved (@k, 24 Sep 2026, chat I1.1, option (a)). LANDING IN PROGRESS on branch `ccr-05`:
  step 1 is done; steps 2-4 are pending. Merge `ccr-05` only when step 4 is green.

Landing steps:
  1. I1 (done, one commit on `ccr-05`): declarations.py reason = template; `make goldens` (diff: ENC-C1_1000.json, 1 line;
     no other scenario, review sheet or held-out file changes); CCR05 override removed from test_api_real_engine.py.
     Resulting state, RED BY DESIGN:
       - `make test`: 2 failed, 134 passed, 1 skipped. NI 1 = e2e smoke. REAL 1 =
         tests/governance/test_governance.py::test_approval_verify_and_offline_clis.
       - `--verify` prints `APPROVAL_v1: report_not_reproducible`.
       - The runtime gate still loads v1: it checks the ruleset and registry hashes and the status, and neither file changed.
  2. B4 (on `ccr-05`):
       - Run `uv run python -m noteguard.governance.evaluate --baseline v1 --candidate v1`. It rewrites
         fixtures/labelled_eval/reports/EVAL_v1_vs_v1.{json,md}.
       - Expect "gate passed; report sha256 ba5f0711db400073c73caf1e61972a3f466b86672dcb570ce7be1a267225c725".
         I1 computed this independently into /tmp: the ONLY difference from the committed report is `corpus.sha256`,
         and every metric is unchanged.
       - Set `evaluation_report_sha256` in rulesets/APPROVAL_v1.md to the new hash, and set `status` back to "draft",
         so nobody approves new evidence on @k's behalf. Commit.
  3. @k re-signs in writing, naming the new report hash.
  4. I1 sets `status`, `approver_label` and `approved_on`, then:
       - `--verify` must print `APPROVAL_v1: consistent`;
       - `make test-governance` must give 9 passed;
       - `make test` must show REAL 0.
     Then merge `ccr-05` into `i1-integration`.
