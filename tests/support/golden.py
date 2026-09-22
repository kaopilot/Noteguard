"""Golden fixture loading and EXACT comparison keys (B0; see fixtures/expected/README.md).

Compare with ``assert_same(actual_keys, expected_keys, label)``: set equality, so a
missing flag and an extra flag both fail."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from noteguard.contracts import ids
from noteguard.contracts.types import (
    EncounterSnapshot,
    Flag,
    Ruleset,
    RulesetBundle,
    TermRegistry,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "fixtures" / "expected"
ENCOUNTERS = ROOT / "fixtures" / "encounters"
#: Held-out ENC-A2 (never in the repo before I1). Directory with encounters/ and expected/.
HELDOUT = Path(os.environ.get("NOTEGUARD_HELDOUT_DIR", ROOT / "fixtures" / "heldout"))

SCENARIOS = ("ENC-A1_1130", "ENC-A1_1600", "ENC-A1_1600_rerun", "ENC-B1_1600")


def _dirs(heldout: bool) -> tuple[Path, Path]:
    return (HELDOUT / "expected", HELDOUT / "encounters") if heldout else (EXPECTED, ENCOUNTERS)


def heldout_scenarios() -> tuple[str, ...]:
    exp, _ = _dirs(True)
    return tuple(sorted(p.stem for p in exp.glob("ENC-*.json"))) if exp.is_dir() else ()


def load(name: str, *, heldout: bool = False) -> dict:
    exp, _ = _dirs(heldout)
    return json.loads((exp / f"{name}.json").read_text(encoding="utf-8"))


def _t(value) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def cutoff(g: dict) -> datetime:
    return _t(g["cutoff"])


def evaluated_at(g: dict) -> datetime:
    return _t(g["evaluated_at"])


def snapshot(name: str, *, heldout: bool = False) -> EncounterSnapshot:
    """Fixture snapshot for a scenario, with prior_flags from its prior scenario (golden)."""
    g = load(name, heldout=heldout)
    _, enc_dir = _dirs(heldout)
    raw = json.loads((enc_dir / f"{g['encounter_ref']}.json").read_text(encoding="utf-8"))
    if g["prior_scenario"]:
        raw["prior_flags"] = load(g["prior_scenario"], heldout=heldout)["flags"]
    return EncounterSnapshot.model_validate(raw)


def bundle() -> RulesetBundle:
    """Ruleset v1 + registry v1 WITHOUT the approval check (tests only; the runtime path
    must go through B4's approval check)."""
    rs = (ROOT / "rulesets" / "v1.json").read_bytes()
    reg = (ROOT / "rulesets" / "registry_v1.json").read_bytes()
    return RulesetBundle(ruleset=Ruleset.model_validate_json(rs), registry=TermRegistry.model_validate_json(reg),
                         ruleset_sha256=ids.sha256_hex(rs), registry_sha256=ids.sha256_hex(reg))


def run(eng, name: str, *, heldout: bool = False):
    """Run the engine on a golden scenario exactly as the goldens assume."""
    g = load(name, heldout=heldout)
    snap = snapshot(name, heldout=heldout)
    b = bundle()
    result = eng.run_checks(snap, b, cutoff(g), run_id=g["run_id"], evaluated_at=evaluated_at(g))
    return g, snap, b, result


# --- comparison keys -------------------------------------------------------------------

def _d(obj) -> dict:
    return obj if isinstance(obj, dict) else obj.model_dump(mode="json", by_alias=True)


def evidence_key(e) -> tuple:
    e = _d(e)
    return (e["note_version_id"], e["start"], e["end"], e["page"], e["quote"], e["quote_sha256"],
            e["role_in_flag"], e["evidence_revision"])


FLAG_FIELDS = ("flag_id", "rule_id", "tier", "category", "lens", "title", "subject_key", "owner_staff_id", "state",
               "revision", "evidence_revision", "source_changed_since_flag", "new_evidence_since_decision",
               "ready_for_clinician", "check_version", "first_run_id", "last_run_id")


def flag_key(f) -> tuple:
    d = _d(f)
    return (tuple((k, d[k]) for k in FLAG_FIELDS) + (("created_at", _t(d["created_at"])),)
            + (("affected", frozenset(d["affected_contributor_ids"])), ("has_question", d["question"] is not None),
               ("evidence", frozenset(evidence_key(e) for e in d["evidence"]))))


def bubble_key(b) -> tuple:
    d = _d(b)
    a = d["absence"]
    absence = None if a is None else (a["status"], a["registry_version"], _t(a["cutoff"]), frozenset(a["terms_searched"]),
                                      frozenset((s["note_version_id"], s["extraction_status"]) for s in a["sources_searched"]))
    return (d["bubble_id"], d["question_template_id"], d["subject_key"], d["status"], d["flag_id"], d["rank"],
            _t(d["cutoff"]), frozenset(evidence_key(e) for e in d["evidence"]), absence)


def claim_key(c) -> tuple:
    d = _d(c)
    return (d["template"], frozenset(d["params"].items()), frozenset(evidence_key(e) for e in d["evidence"]))


def summary_key(s) -> tuple:
    d = _d(s)
    return (d["encounter_id"], d["encounter_ref"], d["patient_ref"], _t(d["cutoff"]), _t(d["generated_at"]),
            d["ruleset_version"], d["registry_version"], d["closure_status"], d["human_review_statement"],
            d["stale_after_source_change"], tuple(tuple(sorted(t.items())) for t in d["timeline"]))


def run_key(r) -> tuple:
    d = _d(r)
    return tuple((k, _t(v) if k in ("source_cutoff", "started_at", "completed_at") else v) for k, v in sorted(d.items()))


def assert_same(actual: list | tuple, expected: list | tuple, label: str) -> None:
    a, e = set(actual), set(expected)
    assert len(a) == len(actual), f"{label}: duplicate items in actual output"
    missing, extra = e - a, a - e
    assert not missing and not extra, (
        f"{label}: exact set equality failed\n  MISSING ({len(missing)}): {sorted(map(repr, missing))[:5]}\n"
        f"  EXTRA ({len(extra)}): {sorted(map(repr, extra))[:5]}")


def assert_required_changes(result, g: dict) -> None:
    """Each golden required change is present (the one 'contains' comparison)."""
    spans = {a.assertion_id: (a.source_version_id, a.span.start, a.span.end) for a in result.assertions}
    have = {(c.kind.value, c.subject_key, spans.get(c.from_assertion_id), spans.get(c.to_assertion_id))
            for c in result.changes}
    for c in g["required_changes"]:
        f, t = c["from_evidence"], c["to_evidence"]
        want = (c["kind"], c["subject_key"], (f["note_version_id"], f["start"], f["end"]),
                (t["note_version_id"], t["start"], t["end"]))
        assert want in have, f"required change missing: {c['kind']} {c['subject_key']} {f['quote']!r} -> {t['quote']!r}"


def flags_by_rule(result, rule_id: str) -> list[Flag]:
    return [f for f in result.flags if f.rule_id.value == rule_id]


def assert_scenario(eng, name: str, *, heldout: bool = False) -> None:
    """Full golden comparison for one scenario: run, flags, changes, bubbles, summary."""
    from noteguard.contracts import states

    g, snap, b, r = run(eng, name, heldout=heldout)
    assert run_key(r.run) == run_key(g["run"]), f"{name}: CheckRun differs"
    assert_same([flag_key(f) for f in r.flags], [flag_key(f) for f in g["flags"]], f"{name} flags")
    for f in r.flags:
        assert f.state.value not in {"dismissed", "resolved", "accepted", "edited"}, "engine set a human-only state"
    for m in g["must_not_flag"]:
        hits = [f for f in r.flags if m["rule_id"] in ("*", f.rule_id.value)
                and m["subject_key"] in ("*", "encounter", f.subject_key)]
        assert not hits, f"{name}: must-not-flag violated: {m['rule_id']} {m['subject_key']} ({m['why']})"
    assert_required_changes(r, g)
    bubbles = eng.answer_bubbles(snap, r, b, cutoff(g))
    assert_same([bubble_key(x) for x in bubbles], [bubble_key(x) for x in g["bubbles"]], f"{name} bubbles")
    summary = eng.build_summary(snap, r, bubbles, (), b, cutoff(g), generated_at=evaluated_at(g))
    assert summary_key(summary) == summary_key(g["summary"]), f"{name}: summary header/timeline differs"
    assert_same([claim_key(c) for c in summary.claims], [claim_key(c) for c in g["summary"]["claims"]], f"{name} claims")
    blocking = {f.flag_id for f in r.flags if states.blocks_closure(f.tier, f.state)}
    assert blocking == {x["flag_id"] for x in g["closure"]["tier1_blockers"]}, f"{name}: closure blockers differ"
