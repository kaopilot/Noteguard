# Decisions (integrator-folded; lanes append to docs/decisions/Bx.md)

Each line: date — decision — reason. All eight OPEN defaults were **confirmed by @k on 22 Sep 2026**
(chat B0.1); an override after CP0 goes through a CCR.

## Open items (Section 16)
- 2026-09-22 — OPEN-1 new repo — confirmed; care-core's Postgres/RLS/worker stack is heavier than a read-only demonstrator; three patterns ported with attribution (egress gate so far, THIRD_PARTY_NOTICES.md).
- 2026-09-22 — OPEN-2 Python 3.12 + FastAPI engine/API; React/TS/Vite PWA — confirmed; pinned in pyproject/uv.lock, .python-version, .nvmrc.
- 2026-09-22 — OPEN-3 per-page-load in-memory workspace, token in JS memory, refresh/reset clears, single process — confirmed; each new workspace is seeded with the synthetic ENC-A1/ENC-B1 case (B2 tests assume this).
- 2026-09-22 — OPEN-4 suppression semantics per Section 8.5 — confirmed and encoded: not raised if the response exists at evaluation time; superseded (never resolved) after a human could see it; Tier 1 superseded still blocks (`contracts/states.py`, golden `ENC-A1_1600_rerun`).
- 2026-09-22 — OPEN-5 AI off by default — confirmed (`AIDraftStatus.DISABLED`; stub reports "AI drafting disabled").
- 2026-09-22 — OPEN-6 accepted Tier 1 still blocks closure — confirmed (`states.blocks_closure`).
- 2026-09-22 — OPEN-7 only the responsible clinician may dismiss/resolve Tier 1, with a reason code — confirmed (`contracts/permissions.py`).
- 2026-09-22 — OPEN-8 thresholds are placeholders pending clinical governance — confirmed (`threshold_status` on every threshold; APPROVAL_v1.md stays draft).

## Decided by @k at CP0 review (22 Sep 2026)
- SpO2 89% / RR 26 stay a DIFF-001 question in v1, not Tier 1; DET-001 is the first stretch rule if time allows (via CCR with goldens) — thresholds are unvalidated and Tier 1 must stay rare (L17).
- OWN-001 carries no quoted span; it cites the empty care-team field with one `encounter_record` evidence item; pinned by the ENC-C1 golden.
- Generated TypeScript types and contract data for B3 (`make types`), and kickoff prompts for B1–B5, added before CP0.
- ENC-A1/ENC-B1 golden scenarios signed off (recorded per scenario in `fixtures/expected/declarations.py`).
- The ruleset is approved at CP2 by @k ("synthetic demo approver") after B4's evaluation; until then the runtime refuses it.
- Repo: a new repo created by @k from the B0 bundle; @k integrates and moves work between chats as bundles.

## Folded from lanes
- 2026-09-22 — B0 decisions 1–32: see docs/decisions/B0.md.
