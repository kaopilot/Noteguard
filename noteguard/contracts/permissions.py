"""Permission matrix as DATA (frozen, B0): role x relation x action x tier -> allow.

B2 enforces this in TWO layers (route dependency AND store methods, L6/L7).
B3 may use it only to hide controls (convenience, never enforcement).
Role lists are defined here and nowhere else (seam test).

Relations are derived server-side for the acting staff member:
  care_team_member       active CareTeamMembership on the encounter
  responsible_clinician  care_team_member AND encounter.responsible_clinician_id == staff_id
  flag_owner             care_team_member AND flag.owner_staff_id == staff_id
A non-member holds no relation and is refused every encounter-scoped action
with 404 not_found (no existence leak, Section 10.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import (
    DecisionAction,
    PermissionAction,
    ReasonCode,
    Relation,
    Role,
    RuleId,
    Tier,
)

A = PermissionAction
R = Relation

CLINICAL_ROLES = frozenset({Role.CLINICIAN, Role.NURSE, Role.PHARMACIST, Role.ALLIED_HEALTH})
TEAM_ROLES = CLINICAL_ROLES | {Role.CLERICAL_STAFF}  # may read an encounter they are a member of
AGGREGATE_ROLES = frozenset({Role.MEDICAL_DIRECTOR, Role.QUALITY_RISK, Role.LEGAL})
NO_CLINICAL_ACCESS_ROLES = frozenset({Role.CLINIC_ADMIN}) | AGGREGATE_ROLES

ALL_TIERS = frozenset({1, 2, 3})
T1 = frozenset({1})
T23 = frozenset({2, 3})


@dataclass(frozen=True)
class PermissionRule:
    action: PermissionAction
    roles: frozenset[Role]
    relations_any: frozenset[Relation]  # actor needs at least one; empty = no encounter scope
    tiers: frozenset[int] | None = None  # None = not tier-scoped


_MEMBER = frozenset({R.CARE_TEAM_MEMBER})
_OWNER_OR_RC = frozenset({R.FLAG_OWNER, R.RESPONSIBLE_CLINICIAN})
_RC = frozenset({R.RESPONSIBLE_CLINICIAN})
_CLIN = frozenset({Role.CLINICIAN})

PERMISSION_RULES: tuple[PermissionRule, ...] = (
    # --- encounter-scoped, not tier-scoped ---
    PermissionRule(A.READ_ENCOUNTER, TEAM_ROLES, _MEMBER),
    PermissionRule(A.ADD_SOURCE, TEAM_ROLES, _MEMBER),
    PermissionRule(A.RUN_CHECKS, TEAM_ROLES, _MEMBER),
    PermissionRule(A.VIEW_SUMMARY, TEAM_ROLES, _MEMBER),
    PermissionRule(A.VIEW_DOCUMENT, TEAM_ROLES, _MEMBER),
    PermissionRule(A.RECORD_FEEDBACK, TEAM_ROLES, _MEMBER),
    PermissionRule(A.RESET_WORKSPACE, TEAM_ROLES, _MEMBER),
    PermissionRule(A.CLOSE_ENCOUNTER, _CLIN, _RC),
    # --- not encounter-scoped ---
    PermissionRule(A.VIEW_AGGREGATE, AGGREGATE_ROLES, frozenset()),
    # --- flag decisions ---
    PermissionRule(A.DECIDE_ACCEPT, _CLIN, _OWNER_OR_RC, T1),
    PermissionRule(A.DECIDE_ACCEPT, CLINICAL_ROLES, _OWNER_OR_RC, T23),
    PermissionRule(A.DECIDE_EDIT, _CLIN, _OWNER_OR_RC, T1),
    PermissionRule(A.DECIDE_EDIT, CLINICAL_ROLES, _OWNER_OR_RC, T23),
    PermissionRule(A.DECIDE_REASSIGN, _CLIN, _OWNER_OR_RC, T1),
    PermissionRule(A.DECIDE_REASSIGN, CLINICAL_ROLES, _OWNER_OR_RC, T23),
    # Staff prepare (L16): any care-team member, any tier.
    PermissionRule(A.DECIDE_MARK_READY, TEAM_ROLES, _MEMBER, ALL_TIERS),
    # Clinicians close (L16, OPEN-7 default): Tier 1 responsible clinician only.
    PermissionRule(A.DECIDE_DISMISS, _CLIN, _RC, T1),
    PermissionRule(A.DECIDE_DISMISS, CLINICAL_ROLES, _OWNER_OR_RC, T23),
    PermissionRule(A.DECIDE_RESOLVE, _CLIN, _RC, T1),
    PermissionRule(A.DECIDE_RESOLVE, CLINICAL_ROLES, _OWNER_OR_RC, T23),
)

DECISION_PERMISSION: dict[DecisionAction, PermissionAction] = {
    DecisionAction.ACCEPT: A.DECIDE_ACCEPT,
    DecisionAction.EDIT: A.DECIDE_EDIT,
    DecisionAction.REASSIGN: A.DECIDE_REASSIGN,
    DecisionAction.MARK_READY_FOR_CLINICIAN: A.DECIDE_MARK_READY,
    DecisionAction.DISMISS: A.DECIDE_DISMISS,
    DecisionAction.RESOLVE: A.DECIDE_RESOLVE,
}

#: Roles a flag may be reassigned TO, by tier (new owner must also be a care-team member).
REASSIGN_TARGET_ROLES: dict[int, frozenset[Role]] = {1: _CLIN, 2: CLINICAL_ROLES, 3: CLINICAL_ROLES}

#: Reason codes allowed per decision action (L15). No free-text-only resolution.
DISMISS_REASONS = frozenset({
    ReasonCode.EXTRACTION_ERROR,
    ReasonCode.ALREADY_ADDRESSED_IN_SOURCE,
    ReasonCode.WRONG_ENCOUNTER,
    ReasonCode.DUPLICATE_OF,
    ReasonCode.NOT_CLINICALLY_RELEVANT,
})
RESOLVE_REASONS = frozenset({
    ReasonCode.RESPONSE_DOCUMENTED_CONFIRMED,
    ReasonCode.ALLERGY_ENTRY_CONFIRMED,
    ReasonCode.INTOLERANCE_NOT_ALLERGY,
    ReasonCode.DOSE_ENTRY_CURRENT,
    ReasonCode.OWNER_AND_TIMING_DOCUMENTED,
    ReasonCode.MANUAL_REVIEW_COMPLETED,
    ReasonCode.OCR_COMPLETED,
    ReasonCode.STATEMENT_CONFIRMED_CURRENT,
    ReasonCode.STATEMENT_CORRECTED_IN_SOURCE,
    ReasonCode.WORK_COMPLETED_DOCUMENTED,
})
REASONS_BY_ACTION: dict[DecisionAction, frozenset[ReasonCode]] = {
    DecisionAction.DISMISS: DISMISS_REASONS,
    DecisionAction.RESOLVE: RESOLVE_REASONS,
}
#: Resolutions that adjudicate between assertions: adjudicated_assertion_ids required (L2).
ADJUDICATION_REASONS = frozenset({
    ReasonCode.ALLERGY_ENTRY_CONFIRMED,
    ReasonCode.INTOLERANCE_NOT_ALLERGY,
    ReasonCode.DOSE_ENTRY_CURRENT,
})
#: Resolve reasons that make sense per rule (a resolve with another code is refused).
RESOLVE_REASONS_BY_RULE: dict[RuleId, frozenset[ReasonCode]] = {
    RuleId.CRIT_001: frozenset({ReasonCode.RESPONSE_DOCUMENTED_CONFIRMED, ReasonCode.WORK_COMPLETED_DOCUMENTED}),
    RuleId.ALG_001: frozenset({ReasonCode.ALLERGY_ENTRY_CONFIRMED, ReasonCode.INTOLERANCE_NOT_ALLERGY}),
    RuleId.DOSE_001: frozenset({ReasonCode.DOSE_ENTRY_CURRENT}),
    RuleId.DOSE_002: frozenset({ReasonCode.WORK_COMPLETED_DOCUMENTED, ReasonCode.STATEMENT_CORRECTED_IN_SOURCE}),
    RuleId.PEND_001: frozenset({ReasonCode.OWNER_AND_TIMING_DOCUMENTED, ReasonCode.WORK_COMPLETED_DOCUMENTED}),
    RuleId.PDF_001: frozenset({ReasonCode.MANUAL_REVIEW_COMPLETED, ReasonCode.OCR_COMPLETED}),
    RuleId.DIFF_001: frozenset({ReasonCode.STATEMENT_CONFIRMED_CURRENT, ReasonCode.STATEMENT_CORRECTED_IN_SOURCE}),
    RuleId.OWN_001: frozenset({ReasonCode.WORK_COMPLETED_DOCUMENTED}),
    RuleId.DET_001: frozenset({ReasonCode.RESPONSE_DOCUMENTED_CONFIRMED, ReasonCode.STATEMENT_CORRECTED_IN_SOURCE}),
    RuleId.LAT_001: frozenset({ReasonCode.STATEMENT_CORRECTED_IN_SOURCE, ReasonCode.WORK_COMPLETED_DOCUMENTED}),
    RuleId.META_001: frozenset({ReasonCode.STATEMENT_CORRECTED_IN_SOURCE}),
    RuleId.NEXT_001: frozenset({ReasonCode.STATEMENT_CORRECTED_IN_SOURCE, ReasonCode.WORK_COMPLETED_DOCUMENTED}),
}

#: No bulk decisions (L15): the decision endpoint takes exactly one flag.
MAX_FLAGS_PER_DECISION = 1


def is_allowed(
    action: PermissionAction,
    role: Role,
    relations: frozenset[Relation] | set[Relation],
    tier: Tier | int | None = None,
) -> bool:
    """Pure lookup over PERMISSION_RULES. Enforcement (and 404-vs-403 choice) is B2's."""
    rel = frozenset(relations)
    for rule in PERMISSION_RULES:
        if rule.action != action or role not in rule.roles:
            continue
        if rule.relations_any and not (rel & rule.relations_any):
            continue
        if rule.tiers is not None:
            if tier is None or int(tier) not in rule.tiers:
                continue
        return True
    return False
