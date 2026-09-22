# Decisions (integrator-folded; lanes append to docs/decisions/Bx.md)

Each line: date — decision — reason. "Default adopted" means B0 built on the Section 16
recommendation; @k confirms or overrides at CP0 (an override after CP0 goes through a CCR).

## Open items (Section 16)
- 2026-09-22 — OPEN-1 new repo — default adopted; care-core's Postgres/RLS/worker stack is heavier than a read-only demonstrator; three patterns ported with attribution (egress gate so far, THIRD_PARTY_NOTICES.md).
- 2026-09-22 — OPEN-2 Python 3.12 + FastAPI engine/API; React/TS/Vite PWA — default adopted; pinned in pyproject/uv.lock, .python-version, .nvmrc.
- 2026-09-22 — OPEN-3 per-page-load in-memory workspace, token in JS memory, refresh/reset clears, single process — default adopted; each new workspace is seeded with the synthetic ENC-A1/ENC-B1 case (B2 tests assume this).
- 2026-09-22 — OPEN-4 suppression semantics per Section 8.5 — default adopted and encoded: not raised if the response exists at evaluation time; superseded (never resolved) after a human could see it; Tier 1 superseded still blocks (`contracts/states.py`, golden `ENC-A1_1600_rerun`).
- 2026-09-22 — OPEN-5 AI off by default — default adopted (`AIDraftStatus.DISABLED`; stub reports "AI drafting disabled").
- 2026-09-22 — OPEN-6 accepted Tier 1 still blocks closure — default adopted (`states.blocks_closure`).
- 2026-09-22 — OPEN-7 only the responsible clinician may dismiss/resolve Tier 1, with a reason code — default adopted (`contracts/permissions.py`).
- 2026-09-22 — OPEN-8 thresholds are placeholders pending clinical governance — default adopted (`threshold_status` on every threshold; APPROVAL_v1.md stays draft).

## Folded from lanes
- 2026-09-22 — B0 decisions 1–24: see docs/decisions/B0.md (fold at CP0).
