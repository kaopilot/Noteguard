# I1 integration checklist (@k as integrator)

1. Merge in CP1 order B1 → B2 → B4 → B3; after each: `make test` (tally must show 0 REAL failures), fold `docs/decisions/Bx.md` into `docs/DECISIONS.md`.
2. Swap the stub engine: B2's engine seam points at `noteguard.engine.get_engine()` (B1). The B0 stub stays in the repo for reference.
3. Install the held-out case: unpack `noteguard_heldout_ENC-A2.zip` into `fixtures/heldout/`, check `MANIFEST.sha256` against `fixtures/heldout/README.md`, run `uv run pytest tests/engine/test_heldout_golden.py -v`, then commit it in one `[I1.n]` commit.
4. Rerun `test_open_count_integrity` and `test_grounding` against the real API (I1 owns the API-level runs).
5. Run B4's `evaluate.py` on the final ruleset and registry; if the Tier 1 recall gate passes, set `rulesets/APPROVAL_v1.md` to approved with the current hashes (label "synthetic demo approver").
6. Land the E2E smoke test (`tests/e2e/`), then `make test` from a fresh clone before code freeze (Thu 08:00 SGT).
