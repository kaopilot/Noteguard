# Approval record — ruleset v1 / registry v1

**Status: DRAFT.** Not approved. B1 is still filling rule and term content, so the hashes
below are the B0 seed hashes and will change. The runtime (B4) must refuse to load a
ruleset whose file hashes do not match an `approved` record here.

Approval flow (Section 11): version → offline evaluation (`governance/evaluate.py`) →
clinical governance approval (this record, with the evaluation report hash) → pinned
release → rollback by re-pinning the previous approved version.

Critical-value and deterioration thresholds in `registry_v1.json` are
**placeholders pending clinical governance sign-off** (OPEN-8).

The machine-readable record is the single fenced JSON block below. B4 parses it; it
validates against `noteguard.contracts.types.ApprovalRecord`.

```json
{
  "ruleset_version": "v1",
  "ruleset_sha256": "4668c53693d70c0a1c505ee3350e1623a8ec0700b65e72268ea1197d6f792888",
  "registry_version": "v1",
  "registry_sha256": "2fcf71c54366d848f914a314640dae10dc181eb1a19e277027bf4b7d0e5f7cd6",
  "evaluation_report_sha256": null,
  "approver_role": "clinical_governance",
  "approver_label": "Synthetic demo approver (pending @k sign-off)",
  "approved_on": "2026-09-22",
  "status": "draft"
}
```
