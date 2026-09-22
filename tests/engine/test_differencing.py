"""Required test 8. owner: B1."""

import pytest

from noteguard.contracts.forbidden_phrases import find_forbidden
from tests.support import golden
from tests.support.builders import Note, build_snapshot, run_synthetic
from tests.support.golden import flags_by_rule
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]


def test_differencing():
    """Mutations: treat explicit change language as a contradiction -> DOSE-001 on metformin;
    drop the 'contradicting assertion in between' condition -> the benign copy raises DIFF-001."""
    eng = engine()
    g, _, _, r = golden.run(eng, "ENC-A1_1600")
    (d,) = flags_by_rule(r, "DIFF-001")
    assert {e.role_in_flag.value: e.quote for e in d.evidence} == {
        "claim": "Patient stable", "origin": "Patient stable", "counter_claim": "SpO2 89% on room air, RR 26"}
    assert len({e.source_version_id for e in d.evidence}) == 3  # both spans side by side + the contradiction
    assert d.question and d.question.rstrip().endswith("?") and find_forbidden(d.question) is None
    assert not [f for f in r.flags if f.rule_id.value == "DOSE-001" and f.subject_key == "drug:metformin"]
    golden.assert_required_changes(r, g)  # explicit_change metformin, carried_forward stable, reworded metformin
    benign = build_snapshot([Note("wr", "09:00", "lim", "Patient stable."),
                             Note("obs", "13:00", "ravi", "SpO2 97% on room air, RR 16."),
                             Note("sw", "16:00", "goh", "Patient stable.")], ref="ENC-T-CF-OK")
    assert flags_by_rule(run_synthetic(eng, benign), "DIFF-001") == [], "consistent carried text needs no question"
