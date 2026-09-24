# CCR-03 — Export the 409 `StaleRevision` body to the generated types
Raised by: B3, session B3.1   Date: 23 Sep 2026
What changes (files, fields, values):
  - `noteguard/api/routes/core.py` (B2): declare `responses={409: {"model": StaleRevision}}` on the
    FLAG_DECISIONS route so the model appears in `docs/openapi.json`.
  - Integrator: `make types` (openapi.json, schema.gen.ts). Additive only; no field changes.
Why (the failing case or missing capability):
  `StaleRevision` (types.py) is the frozen 409 body for a stale `expected_revision`: current state
  and the other actor's decision (feedback item 10). It is not in openapi.json, so it is missing from
  `frontend/src/api/schema.gen.ts`. B3 must show "Dr Lim accepted this at 16:05". Until this lands,
  B3 reads the body through a local structural type (`StaleBody` in DecisionSheet.tsx) whose fields
  are all optional and typed with generated enums (`DecisionAction`, `FlagState`). This is a local
  stub behind the contract, declared in docs/decisions/B3.md #12.
Lanes affected and what each must do:
  - B2: add the `responses=` declaration (no behaviour change).
  - Integrator: `make types`; `test_openapi_export_in_sync` and `test_generated_types` stay green.
  - B3: replace `StaleBody` with `components['schemas']['StaleRevision']`.
Golden fixture impact: none.
Status: approved (@kaopilot, 23 Sep 2026). LANDED: B2 part and make types in B2.4 (7e28958, 282f65a; merged 894ada7);
  B3 part in B3.2 (cd31f04: the generated `StaleRevision` replaces the local type). Status line updated by I1
  (session I1.4, 24 Sep 2026) at @kaopilot's request.
