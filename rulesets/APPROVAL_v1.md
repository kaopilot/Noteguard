# Approval record — ruleset v1 / registry v1

**Status: APPROVED** (24 Sep 2026, CCR-05 step 3: @kaopilot re-signed on report sha256 `ba5f0711…` by written
authorisation in chat session I1.2, "you can sign for me"; recorded by I1 after checking that the committed
report's hash equals I1's independent recomputation and that only `corpus.sha256` changed). @kaopilot first approved
this record on 24 Sep 2026 (chat I1.1) on report `81cc969e…`. The runtime (`noteguard.governance.approval`) refuses to load a
ruleset unless this record is `approved`, names an evaluation report, and its hashes equal the
bytes of `rulesets/v1.json` and `rulesets/registry_v1.json` (checked on every load).

Prepared by B4 (session B4.1, 23 Sep 2026) for @kaopilot's CP2 decision: the hashes below are the current
files after CCR-01 and CCR-02, and `evaluation_report_sha256` is the report
`fixtures/labelled_eval/reports/EVAL_v1_vs_v1.json` (gate PASSED; Tier 1 recall 17/17 on the gated
corpus; engine `noteguard.engine.engine.Engine`). The report hash is the sha256 of its canonical
JSON (`noteguard.contracts.ids.canonical_json`); rerun
`uv run python -m noteguard.governance.evaluate --baseline v1 --candidate v1` and compare.

**To approve (CP2, after I1 reruns the evaluation on the final ruleset and registry):** rerun the
evaluation; if the gate passes and the hashes below still match, set `status` to `approved`,
`approver_label` to `Synthetic demo approver`, `approved_on` to the date. If any file changed,
refresh the hashes first. Rollback = re-pin the previous approved version.

Approval flow (Section 11): version → offline evaluation (`governance/evaluate.py`) →
clinical governance approval (this record, with the evaluation report hash) → pinned
release → rollback by re-pinning the previous approved version.

Critical-value and deterioration thresholds in `registry_v1.json` are
**placeholders pending clinical governance sign-off** (OPEN-8).

The machine-readable record is the single fenced JSON block below. It validates against
`noteguard.contracts.types.ApprovalRecord`.

```json
{
  "ruleset_version": "v1",
  "ruleset_sha256": "0735b10020c435cbc580e6e6ddf7d3f5b01f4dbea4a9284543a5e1060880ff20",
  "registry_version": "v1",
  "registry_sha256": "3ff6c6129d310cce76f9831a84d1d789fbaa72f1b88a0dc2675e3917a308bb8b",
  "evaluation_report_sha256": "ba5f0711db400073c73caf1e61972a3f466b86672dcb570ce7be1a267225c725",
  "approver_role": "clinical_governance",
  "approver_label": "Synthetic demo approver",
  "approved_on": "2026-09-24",
  "status": "approved"
}
```
