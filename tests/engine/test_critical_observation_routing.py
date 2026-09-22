"""Required test 1. owner: B1 (I1 adds an API-level run)."""

import pytest

from tests.support import golden
from tests.support.builders import Note, build_snapshot, run_synthetic, staff_id
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]


def _crit(result, analyte="analyte:potassium"):
    return [f for f in result.flags if f.rule_id.value == "CRIT-001" and f.subject_key == analyte]


BASE = [Note("obs", "11:15", "tan", "Potassium 6.4 mmol/L."), Note("unrel", "11:20", "chen", "Walked 20 m with frame.")]


def test_critical_observation_routing():
    """Mutations that must make this fail: drop the 'later than the observation' check; drop the
    carried-forward check in suppression; drop negation scope; suppress on any analyte."""
    eng = engine()
    # K 6.4 in a nursing note, no response (the 11:15 note says "Not yet reviewed") -> Tier 1, owner RC
    _, snap, _, r = golden.run(eng, "ENC-A1_1130")
    (f,) = _crit(r)
    assert int(f.tier) == 1 and f.state.value == "open"
    assert f.owner_staff_id == snap.encounter.responsible_clinician_id
    assert [e.quote for e in f.evidence if e.role_in_flag.value == "claim"] == ["Potassium 6.4 mmol/L"]
    assert staff_id("tan") in f.affected_contributor_ids  # source-note owner stays visible
    # later clinician note documents review/treatment/repeat -> not raised
    _, _, _, r16 = golden.run(eng, "ENC-A1_1600")
    assert _crit(r16) == []

    earlier = build_snapshot([Note("early", "09:00", "lim", "K reviewed, treated per protocol.")] + BASE, ref="ENC-T-EARLY")
    assert len(_crit(run_synthetic(eng, earlier))) == 1, "an EARLIER 'reviewed' note must not suppress"
    carried = build_snapshot([Note("early", "09:00", "lim", "K 6.4 reviewed, treated per protocol.")] + BASE
                             + [Note("copy", "14:00", "ravi", "Handover.\nK 6.4 reviewed, treated per protocol.")],
                             ref="ENC-T-CF")
    assert len(_crit(run_synthetic(eng, carried))) == 1, "a CARRIED-FORWARD 'reviewed' line must not suppress"
    negated = build_snapshot(BASE + [Note("neg", "13:00", "lim", "K 6.4 not yet reviewed.")], ref="ENC-T-NEG")
    assert len(_crit(run_synthetic(eng, negated))) == 1, "a NEGATED response must not suppress"
    other = build_snapshot(BASE + [Note("resp", "13:00", "lim", "Sodium reviewed, treated per protocol.")], ref="ENC-T-OTHER")
    assert len(_crit(run_synthetic(eng, other))) == 1, "a response for a DIFFERENT analyte must not suppress"
    later = build_snapshot(BASE + [Note("resp", "13:00", "lim", "K 6.4 reviewed, treated per protocol.")], ref="ENC-T-OK")
    assert _crit(run_synthetic(eng, later)) == [], "a later, new, non-negated same-analyte response suppresses"
