# CCR-01 — Dose-unit canonical forms in the term registry schema
Raised by: B1, session B1.1   Date: 2026-09-22

What changes (files, fields, values):
  `noteguard/contracts/types.py` `TermRegistry`: add
  `dose_unit_canonical: dict[str, tuple[str, float]] = {}` mapping each registry dose unit to
  (canonical unit, factor), e.g. `"g": ("mg", 1000)`, `"mcg": ("mg", 0.001)`,
  `"tabs": ("tablet", 1)`. `rulesets/registry_v1.json` gains the matching entries (B1 content).
  Schema default `{}` keeps every existing registry valid.

Why (the failing case or missing capability):
  DOSE-001 must treat `metformin 0.5 g` and `Metformin 500 mg` as the same dose
  (`test_cross_note_conflicts`). The registry lists which strings ARE dose units but not how they
  relate, so B1 keeps that arithmetic in `noteguard/engine/units.py` (metric mass prefixes and
  plural folding only; recognition still comes from the registry). This is a second, small home
  for unit knowledge, which is the kind of seam L5 warns about. Moving it into the registry makes
  it versioned, approved and visible to governance (B4's evaluation).
  Safety note on the current stub: a unit the table cannot fold is compared as written, so an
  unfamiliar unit can only make two regimens look different (flag), never the same (pass).

Lanes affected and what each must do:
  B0/integrator: land the schema field and regenerate `make types`.
  B1: move the table from `engine/units.py` into `registry_v1.json`; delete the engine copy.
  B4: refresh the approval hash at CP2 (registry content changes).
  B2, B3: none.

Golden fixture impact: none (no flag, bubble or claim changes; verified by the B1 golden run).

Status: proposed
