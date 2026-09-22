"""Required test 3. owner: B1."""

import pytest

from tests.support import golden
from tests.support.builders import Note, build_snapshot, run_synthetic, staff_id
from tests.support.golden import flags_by_rule
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]

CASES = {
    "owner_only": ("Blood culture sent; Dr Lim to review.", 1),
    "timing_only": ("Blood culture sent, to chase by end of shift.", 1),
    "neither": ("Blood culture sent, awaiting result.", 1),
    "both": ("Blood culture sent; Dr Lim to review by 18:00.", 0),
}


def test_pending_owner_and_time():
    """Mutation: accept owner OR timing instead of AND -> owner_only / timing_only stop flagging."""
    eng = engine()
    for name, (text, n) in CASES.items():
        s = build_snapshot([Note("ward", "09:00", "lim", text), Note("u", "09:30", "chen", "Walked 20 m with frame.")],
                           ref=f"ENC-T-PEND-{name}")
        pend = flags_by_rule(run_synthetic(eng, s), "PEND-001")
        assert len(pend) == n, f"{name}: {text!r}"
        if n:
            assert pend[0].subject_key == "test:blood_culture" and int(pend[0].tier) == 2
            assert pend[0].owner_staff_id == staff_id("lim")  # single source -> source-note owner
    linked = build_snapshot([Note("ward", "09:00", "lim", "Blood culture sent, awaiting result."),
                             Note("later", "10:00", "tan", "Blood culture: Dr Lim to review result by 18:00.")],
                            ref="ENC-T-PEND-LINK")
    assert flags_by_rule(run_synthetic(eng, linked), "PEND-001") == [], "a linked later statement supplies both"
    _, _, _, r = golden.run(eng, "ENC-A1_1600")
    assert [f.subject_key for f in flags_by_rule(r, "PEND-001")] == ["test:blood_culture"]
