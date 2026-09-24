# Decisions (integrator-folded at checkpoints; finalised by B5 in session B5.1, 24 Sep 2026)

Each line: date — decision — reason. All eight OPEN defaults were **confirmed by @kaopilot on 22 Sep 2026**
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

## Decided by @kaopilot at CP0 review (22 Sep 2026)
- SpO2 89% / RR 26 stay a DIFF-001 question in v1, not Tier 1; DET-001 is the first stretch rule if time allows (via CCR with goldens) — thresholds are unvalidated and Tier 1 must stay rare (L17).
- OWN-001 carries no quoted span; it cites the empty care-team field with one `encounter_record` evidence item; pinned by the ENC-C1 golden.
- Generated TypeScript types and contract data for B3 (`make types`), and kickoff prompts for B1–B5, added before CP0.
- ENC-A1/ENC-B1 golden scenarios signed off (recorded per scenario in `fixtures/expected/declarations.py`).
- The ruleset is approved at CP2 by @kaopilot ("synthetic demo approver") after B4's evaluation; until then the runtime refuses it.
- Repo: a new repo created by @kaopilot from the B0 bundle; @kaopilot integrates and moves work between chats as bundles.


## Owner handle
- 2026-09-24 — The owner's handle is **@kaopilot**. Records written before this date said "@k"; at @kaopilot's request I1 replaced it throughout the repo (session I1.6, decisions/I1.md #41). Two hash-pinned places keep "@k" (meaning @kaopilot), because editing them would invalidate a pinned hash: one `must_not_flag` note in `fixtures/expected/ENC-A1_1600.json` (with its source line in `declarations.py` and the review-sheet line generated from it), which is inside the approved evaluation corpus, and the held-out package `fixtures/heldout/` (manifest-pinned). Git commit messages are unchanged.
- Those records are left verbatim. They are other lanes' append-only records (18.4). Also, `fixtures/expected/*.json` and the held-out package feed the evaluation-report hash behind APPROVAL_v1 and the pinned held-out manifest, so editing them would un-verify the approval (the CCR-05 chain).
- Files B5 writes or finalises use @kaopilot.

## Folded from lanes (one line each; the lane file has the reasoning)
- B0 #1 (22 Sep) — Evidence spans are statement spans defined once in `contracts/spans.py`; known limit: abbreviations such as "e.g." split a statement.
- B0 #3 (22 Sep) — A flag keeps citing the version it cited; a newer version sets `source_changed_since_flag` (feedback 16).
- B0 #20, I1 #2–5 — Held-out ENC-A2 was kept outside the repo until I1, which installed it after checking the pinned manifest. It is now in `main`'s history, so never hand a `main` bundle to a reopened B1 chat.
- B0 #27, CCR-05 — OWN-001 cites the care-team field (`encounter_record` evidence); its golden reason equals the ruleset template.
- B1 #2 — Negation/uncertainty scope: rest of the clause, ≤ 6 tokens, never across ":".
- B1 #8 — An explicit change needs a registry change cue, a clinician or pharmacy author, and a strictly later source time; otherwise it stays a conflict.
- B1 #11 — Near-verbatim copy = difflib token ratio ≥ 0.9 with identical numbers, terms and negations.
- B1 #13–14 — A dismissed or resolved flag reopens only for new evidence from a source not already cited. A finding that is answered becomes superseded, never resolved.
- B1 #19 — The engine never sets `stale_after_source_change`; the API does.
- CCR-01 (B1 #33) — Dose-unit conversions live in the approved registry, not engine code.
- CCR-02 (B1 #26–31) — DET-001 enabled in v1 with hand-written goldens, re-signed by @kaopilot.
- B1 #38–39 — No engine change after the held-out run; B1 later saw two ENC-A2 statements, so a fully independent re-test needs a new held-out case.
- B2 #2–3 — Two-layer authz with two data paths: the route guard reads the seed directory, the store gate reads the workspace copy, and the exact tier/owner rule runs in the store.
- B2 #4, #6 — Random server-side session token (HttpOnly, SameSite=Lax, Path=/api, `secure=False` locally); workspaces keyed by the token's hash; expiry returns 410.
- B2 #8 — Intake is recorded at the server clock (no backdating), so runs are as-of: an earlier cutoff ignores a new note. I1 #28 asks the brief to say so (brief §4).
- B2 #11–12 — Cutoffs never move backwards or into the future. The API refuses to commit an engine result that moves a flag into a human-only state or drops a known flag.
- B2 #14 — Closure blocker lists are compared as sets (the goldens' order is hand-declared).
- B2 #41 — A refused check run (unapproved ruleset) is audited.
- B2 (handoff B2.2) — Workspaces are per user, so two users never share decisions in the demonstrator (OPEN-3 consequence; brief §7).
- B3 #6, #9 — Decided flags sit behind the history toggle; permissions only hide controls; the server decides tiers, owners, states and closure.
- B3 #11 — A span whose converted slice does not equal its quote is not highlighted.
- B3 #34–35 — Node 25+ needs `--no-experimental-webstorage` for jsdom storage tests; `engines` is `^22 || ^24 || ^26`.
- B3 #38 — 503 `ruleset_unapproved` shows as "checks paused for governance approval", never as an outage.
- B3 #46 — Time on screen is measured or null, never invented.
- B3 #57 — The untouched default cutoff sends the exact last recording instant (a rounded value could be in the future and get 422).
- B4 #2 — The approval loader re-verifies on every load and never caches.
- B4 #8–10 — Protected = protected floor or Tier 1 in the baseline. Proposals that lower, disable, narrow or retire a protected rule, or extend a suppressing cue, are refused.
- B4 #17–19 — The evaluation corpus is B4's pre-labelled cases plus the goldens, reported separately. Scoring is exact-set, and a Tier 1 label counts only if raised at Tier 1.
- B4 #23, #42 — Aggregate cells: primary "<5" suppression only; the response-time bucket joins the cell key (CCR-04).
- B4 #28–29, #49 — The AI status reports observed outcomes only. No route calls the drafter; if AI is ever enabled, `/api/ai/status` must report `Drafter.status_view()`.
- B4 #54 — The runtime checks approval status and hashes, not report reproducibility. A stale report is caught by the suite and `--verify` (brief §9).
- I1 #12 — With no bundle loader the real engine gives 501 on every run, so the approval path was the only clean route to CP2.
- I1 #17, #33 — v1 approved on 24 Sep and re-signed after CCR-05 by @kaopilot ("Synthetic demo approver"); I1 recorded both after checking the hashes.
- I1 #26 — Finding #19 (PDF-001 on a failed extraction) was withdrawn: it was an as-of test error. Separately, `tests.support.lanes.real_app()` wires the stub engine, so B2's API suite proves the API layer and I1's tests prove the real engine through it.
- B5.1 — See docs/decisions/B5.md.

Full lane records: docs/decisions/B0.md (1–32), B1.md (1–42), B2.md (1–41), B3.md (1–57), B4.md (1–54), I1.md (1–40), B5.md.
