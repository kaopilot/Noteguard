# Held-out encounter ENC-A2 — for @k and the integrator only

**Do not give this package to any B1 (engine) chat.** It exists to catch an engine that
special-cases ENC-A1 (`if "amlodipine" in text`, fixture offsets, named staff).

Same rules as ENC-A1, with different names (Dr Farah, Nurse Wee, Pharmacist Teo…), drugs
(bisoprolol, atorvastatin), allergen (sulfonamide), analyte (sodium, critical *low*), tests
(urine culture, chest X-ray), times, and phrasing. It also covers cases ENC-A1 does not:
a **partial** 2-page PDF, **DOSE-002** (unparsed dose), a pending item with owner but no
time and another with time but no owner, a `documented` owner bubble, and the "earlier
reviewed" and "carried-forward reviewed" traps sitting inside the record itself.

Contents: `author_heldout.py` (declares the synthetic notes), `declarations.py` (hand-written
expectations), `encounters/ENC-A2.json`, `pdfs/`, `expected/ENC-A2_1200.json`,
`expected/ENC-A2_1730.json`, `expected/REVIEW_SHEET.md` (read this to sign off), `MANIFEST.sha256`.

Install at I1 (after B1's engine is merged):

```bash
mkdir -p fixtures/heldout && cp -r noteguard_heldout_ENC-A2/* fixtures/heldout/
cd fixtures/heldout && sha256sum -c MANIFEST.sha256 && cd -
uv run pytest tests/engine/test_heldout_golden.py -v
```

`fixtures/heldout/*` is git-ignored until then; commit it at I1 in one `[I1.n]` commit.
Assumption: registry v1 contains the six terms B0 added on 22 Sep (bisoprolol, atorvastatin,
sulfonamides class, sulfonamide allergen, urine culture, chest X-ray) and does NOT learn a
drug for the bare statement "4 units given as per chart" (no drug is named, so it stays
unparsed whatever the registry holds).

## Change log

- **22 Sep 2026 — answer key extended by B0 after CCR-02** (DET-001 enabled with the approved
  defaults). ENC-A2 at 17:30 now expects one DET-001 flag (Tier 1, owner Dr Farah) on the 17:00
  "Clinically stable" after the 13:30 low SpO2 / fast RR, and it is added to the summary's open
  priorities and the closure Tier 1 blockers. At 12:00, "must not flag DET-001" is added. Written by
  hand from the rule as approved, after B1 reported an extra DET-001 flag as the only difference;
  every other expected flag, bubble and change is byte-identical to the previous package.

## Exposure log (read before judging the held-out result at I1)

- **22 Sep 2026:** a pasted test run showed the B1 chat two ENC-A2 17:30 statements and their ids.
  B1 said it would not use them and that the result needed no engine change. Treat any later B1
  change touching DET-001, SpO2/RR or "stable" wording with that in mind. Future reports to B1:
  "passed", or the pattern in general terms only.
