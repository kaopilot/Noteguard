"""State machine and permission matrix behave as Section 8.5/8.7 require. owner: B0."""

from itertools import chain, combinations

import pytest

from noteguard.contracts import permissions as P
from noteguard.contracts import states as S
from noteguard.contracts.types import DecisionAction, FlagState, PermissionAction, Relation, Role

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]
REL_SETS = [frozenset(c) for c in chain.from_iterable(combinations(list(Relation), n) for n in range(4))]
TIERS = (None, 1, 2, 3)


def test_engine_never_targets_human_states():
    for table in S.ENGINE_TRANSITIONS.values():
        assert not set(table.values()) & S.ENGINE_FORBIDDEN_TARGETS
    for bad in (("supersede", FlagState.DISMISSED), ("supersede", "resolved"), ("resolve", "open")):
        with pytest.raises(S.InvalidTransition):  # never AttributeError / KeyError (would surface as a 500)
            S.engine_target(*bad)
    with pytest.raises(S.InvalidTransition):
        S.decision_target("accept", "dismissed")
    assert S.decision_target("dismiss", "superseded") is FlagState.DISMISSED


def test_blocks_closure_truth_table():
    for st in FlagState:
        assert S.blocks_closure(1, st) == (st in {FlagState.OPEN, FlagState.ACCEPTED, FlagState.EDITED, FlagState.SUPERSEDED})
        assert not S.blocks_closure(2, st) and not S.blocks_closure(3, st)
    assert S.decision_target(DecisionAction.RESOLVE, FlagState.SUPERSEDED) is FlagState.RESOLVED  # clinician confirms


def test_every_decision_action_is_governed():
    for a in DecisionAction:
        assert a in S.DECISION_TRANSITIONS and a in P.DECISION_PERMISSION
    assert S.REASON_REQUIRED == {DecisionAction.DISMISS, DecisionAction.RESOLVE}


def test_admin_and_aggregate_roles_have_no_clinical_access():
    for role in P.NO_CLINICAL_ACCESS_ROLES:
        for action in PermissionAction:
            if action is PermissionAction.VIEW_AGGREGATE:
                continue
            assert not any(P.is_allowed(action, role, rels, t) for rels in REL_SETS for t in TIERS), (role, action)


def test_non_members_are_refused_everything_encounter_scoped():
    for role in Role:
        for action in PermissionAction:
            if action is not PermissionAction.VIEW_AGGREGATE:
                assert not any(P.is_allowed(action, role, frozenset(), t) for t in TIERS), (role, action)


def test_tier1_close_is_responsible_clinician_only():
    for action in (PermissionAction.DECIDE_DISMISS, PermissionAction.DECIDE_RESOLVE):
        for role in Role:
            for rels in REL_SETS:
                if P.is_allowed(action, role, rels, 1):
                    assert role is Role.CLINICIAN and Relation.RESPONSIBLE_CLINICIAN in rels, (action, role, rels)


def test_staff_prepare_clinicians_close():
    member = frozenset({Relation.CARE_TEAM_MEMBER})
    owner = frozenset({Relation.CARE_TEAM_MEMBER, Relation.FLAG_OWNER})
    assert P.is_allowed(PermissionAction.DECIDE_MARK_READY, Role.CLERICAL_STAFF, member, 1)
    assert not P.is_allowed(PermissionAction.DECIDE_RESOLVE, Role.CLERICAL_STAFF, owner, 2)
    assert P.is_allowed(PermissionAction.DECIDE_RESOLVE, Role.PHARMACIST, owner, 2)
    assert not P.is_allowed(PermissionAction.DECIDE_RESOLVE, Role.NURSE, owner, 1)
