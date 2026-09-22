"""Required test 2. owner: B1. Includes dose-phrasing variants (L4) and the fan-out shape (L1)."""

import pytest

from tests.support import golden
from tests.support.builders import Note, build_snapshot, run_synthetic, staff_id
from tests.support.golden import flags_by_rule
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]
UNREL = Note("u", "12:30", "chen", "Walked 20 m with frame.")


def test_cross_note_conflicts():
    """Mutations: choose a winner by source priority (L2) -> no ALG-001; compare raw dose text
    -> the equivalent variants flag; one flag per evidence pair -> the fan-out count fails."""
    eng = engine()
    _, snap, _, r = golden.run(eng, "ENC-A1_1130")
    (alg,) = flags_by_rule(r, "ALG-001")
    assert int(alg.tier) == 1 and len({e.source_version_id for e in alg.evidence}) == 2
    assert {e.quote for e in alg.evidence} == {"Allergies: NKDA (patient reported)",
                                              "Allergy: Penicillin allergy \u2014 rash (per GP records)"}
    (dose,) = flags_by_rule(r, "DOSE-001")
    assert dose.subject_key == "drug:amlodipine" and int(dose.tier) == 2
    assert dose.owner_staff_id == snap.encounter.responsible_clinician_id
    assert staff_id("ong") in dose.affected_contributor_ids  # pharmacy

    same = [("Amlodipine 5mg OD.", "amlodipine 5 mg once daily."), ("Metformin 500 mg BD.", "metformin 0.5 g twice daily.")]
    for i, (a, b) in enumerate(same):
        s = build_snapshot([Note("a", "09:00", "lim", a), Note("b", "10:00", "ong", b), UNREL], ref=f"ENC-T-SAME{i}")
        assert flags_by_rule(run_synthetic(eng, s), "DOSE-001") == [], f"equivalent regimens flagged: {a!r} / {b!r}"
    diff = [("Amlodipine 5mg OD.", "amlodipine 10 mg OD."), ("Metformin 500 mg BD.", "metformin 500 mg once daily.")]
    for i, (a, b) in enumerate(diff):
        s = build_snapshot([Note("a", "09:00", "lim", a), Note("b", "10:00", "ong", b), UNREL], ref=f"ENC-T-DIFF{i}")
        assert len(flags_by_rule(run_synthetic(eng, s), "DOSE-001")) == 1, f"discrepancy not flagged: {a!r} / {b!r}"

    fan = build_snapshot([
        Note("n1", "08:00", "tan", "Allergies: NKDA."), Note("p1", "09:00", "ong", "Penicillin allergy - rash."),
        Note("n2", "10:00", "ravi", "Allergies: NKDA."), Note("p2", "11:00", "lim", "Allergic to penicillin (rash)."),
        Note("n3", "12:00", "tan", "No known drug allergies."), UNREL], ref="ENC-T-FAN")
    alg = flags_by_rule(run_synthetic(eng, fan), "ALG-001")
    assert len(alg) == 1, "one disagreement = one flag (L1)"
    assert sorted(e.role_in_flag.value for e in alg[0].evidence) == ["claim"] * 3 + ["counter_claim"] * 2
