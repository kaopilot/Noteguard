"""DET-001 reassurance after deterioration (stretch; B1.2). owner: B1.

DET-001 is DISABLED in rulesets/v1.json until CCR-02 is approved, so these tests enable it in an
in-memory bundle only (the ruleset file and the goldens are untouched). Written by the engine's
own lane: a regression guard, not independent evidence.
"""

from datetime import timedelta

import pytest

from noteguard.contracts import states
from noteguard.contracts.forbidden_phrases import find_forbidden
from noteguard.contracts.types import FlagState, RuleId, RulesetBundle
from tests.support import golden
from tests.support.builders import Note, at, build_snapshot, fid, staff_id
from tests.support.golden import flags_by_rule
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]
UNREL = Note("u", "12:30", "chen", "Walked 20 m with frame.")
MARKER = Note("obs", "13:00", "ravi", "SpO2 88% on room air.")
REASSURE = Note("sw", "16:00", "goh", "Patient stable.\nFamily meeting booked.")


def det_bundle() -> RulesetBundle:
    b = golden.bundle()
    rules = tuple(r.model_copy(update={"enabled": True}) if r.rule_id is RuleId.DET_001 else r for r in b.ruleset.rules)
    return b.model_copy(update={"ruleset": b.ruleset.model_copy(update={"rules": rules})})


def _run(notes, ref, prior=()):
    snap = build_snapshot(notes + [UNREL], ref=ref, prior_flags=prior)
    return snap, engine().run_checks(snap, det_bundle(), at("23:00"), run_id=fid(f"run/{ref}/{len(prior)}"),
                                     evaluated_at=at("23:00") + timedelta(minutes=1))


CASES = [
    ("raised_without_review", [MARKER, REASSURE], 1),
    ("clinician_review_between", [MARKER, Note("dr", "14:00", "lim", "SpO2 88% reviewed, oxygen commenced."), REASSURE], 0),
    ("nurse_escalation_is_not_clinician_review", [MARKER, Note("rn", "14:00", "tan", "SpO2 88%, escalated to Dr Lim."),
                                                  REASSURE], 1),
    ("review_of_other_analyte", [MARKER, Note("dr", "14:00", "lim", "Potassium reviewed."), REASSURE], 1),
    ("reassurance_before_marker", [Note("wr", "09:00", "lim", "Patient stable."), MARKER], 0),
    ("review_after_reassurance", [MARKER, REASSURE, Note("dr", "17:00", "lim", "SpO2 reviewed, oxygen commenced.")], 1),
    ("carried_review_does_not_count", [Note("dr0", "11:00", "lim", "SpO2 reviewed, oxygen commenced."), MARKER,
                                       Note("dr", "14:00", "lim", "Handover.\nSpO2 reviewed, oxygen commenced."), REASSURE], 1),
    ("queried_reassurance_is_not_one", [MARKER, Note("sw", "16:00", "goh", "Patient stable?")], 0),
    ("no_deterioration", [Note("obs", "13:00", "ravi", "SpO2 97% on room air."), REASSURE], 0),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_det_001_cases(case):
    """Mutations: count any author as a clinician review -> nurse_escalation fails; drop the
    'at or before the reassurance' bound -> review_after_reassurance fails; drop the carried-forward
    check -> carried_review fails; drop 'marker earlier than reassurance' -> reassurance_before_marker fails."""
    name, notes, want = case
    _, r = _run(notes, f"ENC-T-DET-{name[:18]}")
    assert len(flags_by_rule(r, "DET-001")) == want, name


def test_det_001_shape_owner_and_supersede():
    snap, r = _run([MARKER, REASSURE], "ENC-T-DET-SHAPE")
    (f,) = flags_by_rule(r, "DET-001")
    assert int(f.tier) == 1 and f.subject_key == "status:stable" and f.owner_staff_id == snap.encounter.responsible_clinician_id
    assert {(e.role_in_flag.value, e.quote) for e in f.evidence} == {("claim", "Patient stable"),
                                                                    ("counter_claim", "SpO2 88% on room air")}
    assert set(f.affected_contributor_ids) == {staff_id("goh"), staff_id("ravi")}
    assert f.question and f.question.endswith("?") and find_forbidden(f.question) is None and find_forbidden(f.reason) is None
    # a clinician review documented later, before the reassurance -> superseded (never resolved); still blocks
    reviewed = [MARKER, Note("dr", "14:00", "lim", "SpO2 88% reviewed, oxygen commenced."), REASSURE]
    _, r2 = _run(reviewed, "ENC-T-DET-SHAPE", prior=r.flags)
    (g,) = flags_by_rule(r2, "DET-001")
    assert g.flag_id == f.flag_id and g.state is FlagState.SUPERSEDED and states.blocks_closure(g.tier, g.state)
    assert "suppressor" in {e.role_in_flag.value for e in g.evidence}


def test_det_001_disabled_in_v1_and_proposed_golden():
    """v1 keeps DET-001 disabled (goldens unchanged). With it enabled, ENC-A1 at 16:00 gives exactly the
    flag hand-declared in CCR-02: the 16:00 "Patient stable" after the 13:00 SpO2 89% / RR 26, which no
    clinician-authored statement reviews (the 15:30 review concerns potassium)."""
    eng = engine()
    _, _, _, r = golden.run(eng, "ENC-A1_1600")
    assert flags_by_rule(r, "DET-001") == []
    g = golden.load("ENC-A1_1600")
    snap = golden.snapshot("ENC-A1_1600")
    r = eng.run_checks(snap, det_bundle(), golden.cutoff(g), run_id=g["run_id"], evaluated_at=golden.evaluated_at(g))
    (f,) = flags_by_rule(r, "DET-001")
    assert {(e.role_in_flag.value, e.quote) for e in f.evidence} == {("claim", "Patient stable"),
                                                                    ("counter_claim", "SpO2 89% on room air, RR 26")}
    claim = next(e for e in f.evidence if e.role_in_flag.value == "claim")
    src = {v.source_version_id: v.source_id for v in snap.versions}[claim.source_version_id]
    assert next(s.source_time for s in snap.sources if s.source_id == src) == golden.cutoff(g)  # the 16:00 line, not 09:00
