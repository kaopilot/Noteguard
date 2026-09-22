"""Lesson tests L1-L5, L17 and engine-side Section 8 guarantees. owner: B1."""

import ast
import json
from pathlib import Path

import pytest

from noteguard.contracts import states
from noteguard.contracts.types import Decision, FlagState
from tests.support import golden
from tests.support.builders import Note, at, build_snapshot, fid, run_synthetic, staff_id
from tests.support.golden import ROOT, flags_by_rule
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]
ENGINE_DIR = ROOT / "noteguard" / "engine"
UNREL = Note("u", "12:30", "chen", "Walked 20 m with frame.")


def test_conflict_fanout_one_flag():
    """L1. Mutation: key flag identity on the evidence pair -> 4 flags; include evidence in
    flag_id -> the rerun duplicates the flag."""
    eng = engine()
    notes = [Note("n1", "08:00", "tan", "Allergies: NKDA."), Note("p1", "09:00", "ong", "Penicillin allergy - rash."),
             Note("n2", "10:00", "ravi", "No known drug allergies."), Note("p2", "11:00", "lim", "Allergic to penicillin."),
             UNREL]
    r1 = run_synthetic(eng, build_snapshot(notes, ref="ENC-T-L1"))
    (alg,) = flags_by_rule(r1, "ALG-001")
    assert len(alg.evidence) == 4
    r2 = run_synthetic(eng, build_snapshot(notes, ref="ENC-T-L1", prior_flags=r1.flags))
    assert [f.flag_id for f in flags_by_rule(r2, "ALG-001")] == [alg.flag_id], "rerun must not duplicate"


def test_adjudication_converges():
    """L2. A resolved conflict stays resolved on rerun with the same evidence; new contradicting
    evidence from a different source reopens it with a visible marker.
    Mutation: ignore decisions on rerun -> the flag reopens with no new evidence.
    Mutation (added B1.1): ignore the adjudicated entry -> restating the WINNING side from a
    different source reopens the flag (the P7 failure)."""
    eng = engine()
    notes = [Note("nurse", "08:40", "tan", "Allergies: NKDA."), Note("pharm", "10:30", "ong", "Penicillin allergy - rash."), UNREL]
    r1 = run_synthetic(eng, build_snapshot(notes, ref="ENC-T-L2"))
    (alg,) = flags_by_rule(r1, "ALG-001")
    pen = next(e for e in alg.evidence if e.role_in_flag.value == "counter_claim")
    decision = Decision(decision_id=fid("dec/L2"), flag_id=alg.flag_id, encounter_id=fid("encounter/ENC-T-L2"),
                        expected_revision=alg.revision, resulting_revision=alg.revision + 1, action="resolve",
                        actor_staff_id=staff_id("lim"), actor_role="clinician", reason_code="allergy_entry_confirmed",
                        adjudicated_evidence=({"note_version_id": pen.source_version_id, "start": pen.start, "end": pen.end},),
                        from_state="open", to_state="resolved", at=at("12:00"))
    resolved = alg.model_copy(update={"state": FlagState.RESOLVED, "revision": alg.revision + 1})
    prior = tuple(resolved if f.flag_id == alg.flag_id else f for f in r1.flags)
    r2 = run_synthetic(eng, build_snapshot(notes, ref="ENC-T-L2", prior_flags=prior, decisions=(decision,)))
    (again,) = flags_by_rule(r2, "ALG-001")
    assert again.state is FlagState.RESOLVED and not again.new_evidence_since_decision
    restated = notes + [Note("pharm2", "12:30", "lim", "Penicillin allergy - rash.")]
    r2b = run_synthetic(eng, build_snapshot(restated, ref="ENC-T-L2", prior_flags=prior, decisions=(decision,)))
    (still,) = flags_by_rule(r2b, "ALG-001")
    assert still.state is FlagState.RESOLVED and not still.new_evidence_since_decision, \
        "restating the adjudicated (winning) entry must not reopen (L2)"
    more = notes + [Note("nurse2", "13:00", "ravi", "Allergies: NKDA.")]
    r3 = run_synthetic(eng, build_snapshot(more, ref="ENC-T-L2", prior_flags=prior, decisions=(decision,)))
    (reopened,) = flags_by_rule(r3, "ALG-001")
    assert reopened.state is FlagState.OPEN and reopened.new_evidence_since_decision


def test_change_not_contradiction():
    """L3. Mutation: ignore change cues -> DOSE-001 on the explicit change."""
    eng = engine()
    changed = build_snapshot([Note("wr", "09:00", "lim", "Metformin 500 mg BD."),
                              Note("rev", "15:00", "lim", "Metformin increased to 1 g BD."), UNREL], ref="ENC-T-L3a")
    r = run_synthetic(eng, changed)
    assert flags_by_rule(r, "DOSE-001") == []
    assert any(c.kind.value == "explicit_change" and c.subject_key == "drug:metformin" for c in r.changes)
    unexplained = build_snapshot([Note("wr", "09:00", "lim", "Metformin 500 mg BD."),
                                  Note("rev", "15:00", "ong", "Metformin 1 g BD."), UNREL], ref="ENC-T-L3b")
    assert len(flags_by_rule(run_synthetic(eng, unexplained), "DOSE-001")) == 1


def test_unparsed_dose_never_passes():
    """L4. Mutation: silently drop unparsed dose mentions -> no DOSE-002."""
    eng = engine()
    s = build_snapshot([Note("n", "09:00", "tan", "Amlodipine 5 mg OD.\n4 units given as per chart."), UNREL], ref="ENC-T-L4")
    d2 = flags_by_rule(run_synthetic(eng, s), "DOSE-002")
    assert len(d2) == 1 and int(d2[0].tier) == 3 and d2[0].owner_staff_id == staff_id("tan")
    assert [e.quote for e in d2[0].evidence] == ["4 units given as per chart"]


def _registry_phrases() -> set[str]:
    reg = json.loads((ROOT / "rulesets" / "registry_v1.json").read_text(encoding="utf-8"))
    out = {s for t in reg["terms"] for s in t["synonyms"]} | {t["key"] for t in reg["terms"]}
    out |= {d["phrase"] for d in reg["allergy_denials"]} | {f["phrase"] for f in reg["frequencies"]}
    out |= {c for cues in reg["cues"].values() for c in cues if len(c) >= 4}
    return {p.lower() for p in out}


def test_single_term_registry():
    """L5. The engine holds no term, synonym, denial, frequency or cue list of its own; all
    come from the RulesetBundle. Mutation: hard-code "nkda" in the engine -> fails."""
    engine()
    phrases = _registry_phrases()
    hits = []
    for p in ENGINE_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() in phrases:
                hits.append(f"{p.relative_to(ROOT)}:{node.lineno} {node.value!r}")
    assert not hits, "registry vocabulary hard-coded in the engine:\n" + "\n".join(hits)


def test_tier1_never_auto_closed():
    """Section 8.5 / OPEN-4. Mutation: let supersede resolve Tier 1 -> state resolved, closure unblocked."""
    eng = engine()
    for name in golden.SCENARIOS:
        _, _, _, r = golden.run(eng, name)
        assert all(f.state not in states.ENGINE_FORBIDDEN_TARGETS for f in r.flags), name
    _, _, _, r = golden.run(eng, "ENC-A1_1600_rerun")
    (crit,) = flags_by_rule(r, "CRIT-001")
    assert crit.state is FlagState.SUPERSEDED and states.blocks_closure(crit.tier, crit.state)
    assert {e.role_in_flag.value for e in crit.evidence} == {"claim", "suppressor"}


def test_cited_source_edited_side_by_side():
    """Feedback 16 (engine half; B3 renders the side-by-side). Mutation: re-anchor existing
    flags to the newest version -> citations move to v2 and the marker is lost."""
    eng = engine()
    _, snap, _, r = golden.run(eng, "ENC-A1_1600_rerun")
    versions = {v.source_version_id: v for v in snap.versions}
    for rule in ("ALG-001", "DOSE-001"):
        (f,) = flags_by_rule(r, rule)
        assert f.source_changed_since_flag and f.evidence_revision == 1
        cited = [versions[e.source_version_id] for e in f.evidence if e.role_in_flag.value == "counter_claim"]
        assert [v.version for v in cited] == [1], f"{rule} must keep citing medrec v1"
        assert any(v.supersedes_version_id == cited[0].source_version_id for v in snap.versions), "v2 must exist"


FORBIDDEN_IMPORTS = {"fastapi", "starlette", "logging", "os", "pathlib", "io", "socket", "httpx", "requests",
                     "urllib", "subprocess", "shutil", "sqlite3", "time", "noteguard.api", "noteguard.engine_stub"}


def test_engine_is_pure():
    """B1 exit: no web, file, network, clock or logging access. Mutation: `import logging` in a rule."""
    engine()
    bad = []
    for p in ENGINE_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                if any(n == f or n.startswith(f + ".") for f in FORBIDDEN_IMPORTS):
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno} import {n}")
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in {"open", "print", "input"}:
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno} {fn.id}()")
                if isinstance(fn, ast.Attribute) and fn.attr in {"now", "utcnow", "today"}:
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno} .{fn.attr}()")
    assert not bad, "\n".join(bad)
