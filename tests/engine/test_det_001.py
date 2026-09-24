"""DET-001 reassurance after deterioration (stretch; B1.2). owner: B1.

DET-001 is enabled in rulesets/v1.json by CCR-02 (approved @kaopilot, 22 Sep 2026, defaults); its ENC-A1 behaviour
is pinned by the goldens. ``det_bundle()`` still forces it on, so these cases keep testing the rule even if
a later ruleset disables it. Written by the engine's own lane: a regression guard, not independent evidence.
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
    # the response cue shares a clause with SpO2, so only the clinician-author requirement keeps the flag
    ("nurse_review_is_not_clinician_review", [MARKER, Note("rn", "14:00", "tan", "SpO2 88% reviewed and escalated."),
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
    """Mutations: count any author as a clinician review -> nurse_review fails; drop the
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


def test_det_001_enabled_and_protected_in_v1():
    """CCR-02: DET-001 is enabled, Tier 1 and on the protected floor in ruleset v1 (it cannot be lowered or
    switched off without a new approved ruleset). Mutation: set "enabled": false -> fails here and in the goldens."""
    (rule,) = [r for r in golden.bundle().ruleset.rules if r.rule_id is RuleId.DET_001]
    assert rule.enabled and rule.protected_floor and int(rule.default_tier) == 1
