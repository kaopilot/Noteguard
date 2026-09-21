"""Stub engine (B0): returns the golden fixtures, and ONLY the golden fixtures.

Implements contracts.engine_api.EngineAPI so B2 and B3 can build before B1 lands.
For any input that is not exactly a golden scenario (different sources, a different
cutoff, decisions present, unknown prior flags) it raises NotImplementedError rather
than returning a plausible placeholder (L10). I1 replaces it with noteguard.engine.

Known stub limits (documented, not hidden):
- run_id / evaluated_at arguments are ignored; the golden run_id and times are returned.
- CheckRunResult.assertions and .changes are empty: the goldens pin flags, bubbles and
  summary claims, not every assertion. The stub API serves the golden required_changes
  as ChangeViews.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .contracts import ids
from .contracts.types import (
    CheckRun,
    CheckRunResult,
    Decision,
    EncounterSnapshot,
    Flag,
    QuestionBubble,
    RulesetBundle,
    Summary,
)

EXPECTED_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "expected"

STUB_LIMITATION = "stub engine: only the golden scenarios in fixtures/expected are available"


@lru_cache(maxsize=None)
def load_golden(name: str) -> dict:
    return json.loads((EXPECTED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def golden_names() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in EXPECTED_DIR.glob("*.json")))


def _in_scope_hash(snapshot: EncounterSnapshot, cutoff: datetime) -> str:
    """Hash of the in-scope version sha256s, used only to recognise a golden input."""
    shas = []
    for s in snapshot.sources:
        if s.source_time > cutoff:
            continue
        vs = [v for v in snapshot.versions if v.source_id == s.source_id and v.version_time <= cutoff]
        if vs:
            shas.append(max(vs, key=lambda v: v.version).sha256)
    return ids.source_set_hash(shas)


def match_scenario(snapshot: EncounterSnapshot, cutoff: datetime) -> dict:
    if snapshot.decisions:
        raise NotImplementedError(STUB_LIMITATION + " (decisions present)")
    prior = {f.flag_id: (f.state.value, f.revision) for f in snapshot.prior_flags}
    for name in golden_names():
        g = load_golden(name)
        if g["encounter_id"] != snapshot.encounter.encounter_id:
            continue
        if datetime.fromisoformat(g["cutoff"]) != cutoff:
            continue
        if g["run"]["source_set_hash"] != _in_scope_hash(snapshot, cutoff):
            continue
        want_prior = {}
        if g["prior_scenario"]:
            want_prior = {f["flag_id"]: (f["state"], f["revision"]) for f in load_golden(g["prior_scenario"])["flags"]}
        if prior == want_prior:
            return g
    raise NotImplementedError(STUB_LIMITATION)


class StubEngine:
    """EngineAPI implementation backed by fixtures/expected."""

    is_stub = True

    def run_checks(self, snapshot: EncounterSnapshot, bundle: RulesetBundle, cutoff: datetime, *,
                   run_id: str, evaluated_at: datetime) -> CheckRunResult:
        g = match_scenario(snapshot, cutoff)
        return CheckRunResult(run=CheckRun.model_validate(g["run"]),
                              flags=tuple(Flag.model_validate(f) for f in g["flags"]),
                              assertions=(), changes=())

    def answer_bubbles(self, snapshot: EncounterSnapshot, result: CheckRunResult, bundle: RulesetBundle,
                       cutoff: datetime) -> tuple[QuestionBubble, ...]:
        g = match_scenario(snapshot, cutoff)
        return tuple(QuestionBubble.model_validate(b) for b in g["bubbles"])

    def build_summary(self, snapshot: EncounterSnapshot, result: CheckRunResult,
                      bubbles: tuple[QuestionBubble, ...], decisions: tuple[Decision, ...],
                      bundle: RulesetBundle, cutoff: datetime, *, generated_at: datetime) -> Summary:
        if decisions:
            raise NotImplementedError(STUB_LIMITATION + " (decisions present)")
        g = match_scenario(snapshot, cutoff)
        return Summary.model_validate(g["summary"])
