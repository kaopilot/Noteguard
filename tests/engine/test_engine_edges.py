"""Engine edge cases and a non-ENC-A1 variant (B1.1). owner: B1.

Written by the engine's own lane, so this is a REGRESSION guard, not independent evidence
(the held-out ENC-A2 at I1 is the independent check). Every case applies an input and
asserts on the flag count of one rule, with an unrelated note in scope (12.1 shape).
"""

import pytest

from tests.support.builders import Note, build_snapshot, run_synthetic
from tests.support.golden import bundle, flags_by_rule
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]
UNREL = Note("u", "12:30", "chen", "Walked 20 m with frame.")

EDGES = [
    # (id, rule, notes, expected flag count)
    ("negation_stops_at_colon", "DOSE-001",
     [Note("a", "09:00", "lim", "Amlodipine 5 mg OD."), Note("b", "10:00", "ong", "No change: amlodipine 10 mg OD.")], 1),
    ("queried_allergy_vs_denial_flags", "ALG-001",
     [Note("a", "09:00", "tan", "Allergies: NKDA."), Note("b", "10:00", "lim", "?Penicillin allergy - check with GP.")], 1),
    ("unrecognised_denial_is_not_nkda", "ALG-001",
     [Note("a", "09:00", "tan", "Allergies: nil?"), Note("b", "10:00", "ong", "Penicillin allergy - rash.")], 0),
    ("specific_denial_vs_allergy", "ALG-001",
     [Note("a", "09:00", "tan", "Denies penicillin allergy."), Note("b", "10:00", "ong", "Penicillin allergy - rash.")], 1),
    ("denial_alone_no_conflict", "ALG-001", [Note("a", "09:00", "tan", "Allergies: NKDA.")], 0),
    ("bracketed_dose_parsed", "DOSE-002", [Note("a", "09:00", "lim", "Metformin (5000 mg) BD.")], 0),
    ("colon_and_thousands_dose_parsed", "DOSE-002", [Note("a", "09:00", "lim", "Metformin: 5,000 mg BD.")], 0),
    ("unregistered_drug_dose_needs_review", "DOSE-002", [Note("a", "09:00", "tan", "Insulin 6 units given.")], 1),
    ("change_language_by_nurse_stays_conflict", "DOSE-001",
     [Note("a", "09:00", "lim", "Metformin 500 mg BD."), Note("b", "11:00", "tan", "Metformin increased to 1 g BD.")], 1),
    ("same_statement_response_is_not_later", "CRIT-001",
     [Note("a", "09:00", "tan", "Potassium 6.5 mmol/L, Dr Lim informed.")], 1),
    ("queried_critical_value_still_raised", "CRIT-001",
     [Note("a", "09:00", "tan", "Potassium ?6.5 mmol/L (haemolysed).")], 1),
    ("critical_low_threshold", "CRIT-001", [Note("a", "09:00", "tan", "Na 118 mmol/L.")], 1),
    ("negated_pending_cue", "PEND-001", [Note("a", "09:00", "lim", "Blood culture not sent yet.")], 0),
]


@pytest.mark.parametrize("case", EDGES, ids=[c[0] for c in EDGES])
def test_engine_edge(case):
    """Mutations (spot-checked in B1.1): let negation cross ':' -> negation_stops_at_colon;
    drop the '?' in the observation value pattern -> queried_critical_value_still_raised."""
    name, rule, notes, want = case
    r = run_synthetic(engine(), build_snapshot(notes + [UNREL], ref=f"ENC-T-EDGE-{name[:20]}"))
    assert len(flags_by_rule(r, rule)) == want, name


def test_variant_encounter_generalises():
    """A second encounter with other drugs, allergen, analyte and phrasing than ENC-A1. Guards
    against rules keyed to ENC-A1 strings (the held-out ENC-A2 is the real check)."""
    eng = engine()
    notes = [
        Note("adm", "07:50", "ravi", "Admission.\nAllergies: No known drug allergies.\nObs: RR 18, SpO2 96%."),
        Note("wr", "08:30", "lim", "Ward round.\nClinically stable.\nPlan: Bisoprolol 2.5 mg OD; atorvastatin 20mg nocte."
                                   "\nUrine culture sent.\nCXR pending - Dr Lim to chase by 17:00."),
        Note("pharm", "09:40", "ong", "Med rec: Sulfa allergy (hives).\nbisoprolol 5 mg once daily."),
        Note("lab", "10:20", "tan", "Na 118 mmol/L. K+ 4.1 mmol/L."),
        Note("obs2", "12:00", "ravi", "RR 28, SpO2 93% on 2L."),
        Note("clin", "13:10", "lim", "Sodium 118 reviewed, repeat sent by Dr Lim, recheck at 18:00."
                                     "\nAtorvastatin reduced to 10 mg nocte."),
        Note("sw2", "15:00", "goh", "Clinically stable.\nFamily meeting booked."),
    ]
    snap = build_snapshot(notes, ref="ENC-T-VARIANT")
    r = run_synthetic(eng, snap, "16:00")
    got = {(f.rule_id.value, f.subject_key.split("@")[0]) for f in r.flags}
    # DET-001 (enabled by CCR-02): "Clinically stable" at 15:00 follows RR 28 at 12:00, and the only clinician
    # review in between (13:10) concerns sodium, not RR.
    assert got == {("ALG-001", "allergen:sulfonamide"), ("DOSE-001", "drug:bisoprolol"),
                   ("PEND-001", "test:urine_culture"), ("DIFF-001", "status:stable"), ("DET-001", "status:stable")}
    assert any(c.kind.value == "explicit_change" and c.subject_key == "drug:atorvastatin" for c in r.changes)
    crit = [b for b in eng.answer_bubbles(snap, r, bundle(), r.run.source_cutoff) if b.question_template_id == "q_crit_response"]
    assert [(b.subject_key, b.status.value) for b in crit] == [("analyte:sodium", "documented")]
