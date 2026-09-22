"""Authorisation (B2; L6/L7, Section 10.1). Two layers, two data paths.

ROUTE layer: ``encounter_route_guard`` (a FastAPI dependency on every encounter-scoped route)
checks care-team scope + role against the care-team DIRECTORY built from the seed at startup.
STORE layer: every WorkspaceStore method that reads or mutates encounter data re-checks scope
+ role against the workspace's OWN copy of the encounter and memberships, and the tier/owner
specific decision permission (the route layer only knows whether the role could ever take the
action). Removing the route guard (fault injection) leaves every refusal in place at the store.

Out of scope -> 404 not_found (no existence leak); in scope, wrong role -> 403 forbidden_role.
Both layers use the pure matrix in contracts/permissions.py; relations are derived here, once.
Known limit (L7): both layers share ``relations()``; a bug there affects both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Cookie, Depends, Header, Request

from noteguard.contracts import permissions
from noteguard.contracts import routes as R
from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.types import (
    AuditAction,
    AuditOutcome,
    AuditTargetType,
    CareTeamMembership,
    DecisionAction,
    Encounter,
    PermissionAction,
    Relation,
    Staff,
    Tier,
)

from .errors import ApiError
from .logs import request_bag
from .settings import utcnow

A = PermissionAction


@dataclass(frozen=True)
class AuthContext:
    """Who is acting, in which per-page-load workspace. The token itself is never kept here."""

    staff: Staff
    workspace_id: str
    workspace_hash: str  # sha256 of the workspace token (store key; loggable)


@dataclass(frozen=True)
class EncounterFacts:
    encounter: Encounter
    memberships: tuple[CareTeamMembership, ...]


def active_member(staff: Staff, facts: EncounterFacts, now: datetime) -> bool:
    enc = facts.encounter
    if staff.clinic_id != enc.clinic_id:
        return False
    return any(m.encounter_id == enc.encounter_id and m.staff_id == staff.staff_id and m.valid_from <= now
               and (m.valid_to is None or now < m.valid_to) for m in facts.memberships)


def relations(staff: Staff, facts: EncounterFacts, now: datetime, *, flag_owner_id: str | None = None) -> frozenset[Relation]:
    """Access is by active care-team membership, never by authorship or clinic role."""
    if not active_member(staff, facts, now):
        return frozenset()
    rel = {Relation.CARE_TEAM_MEMBER}
    if facts.encounter.responsible_clinician_id == staff.staff_id:
        rel.add(Relation.RESPONSIBLE_CLINICIAN)
    if flag_owner_id is not None and flag_owner_id == staff.staff_id:
        rel.add(Relation.FLAG_OWNER)
    return frozenset(rel)


def check_encounter_action(staff: Staff, facts: EncounterFacts, action: PermissionAction, now: datetime) -> frozenset[Relation]:
    rel = relations(staff, facts, now)
    if Relation.CARE_TEAM_MEMBER not in rel:
        raise ApiError(ErrorCode.NOT_FOUND)
    if not permissions.is_allowed(action, staff.role, rel):
        raise ApiError(ErrorCode.FORBIDDEN_ROLE)
    return rel


def check_decision(staff: Staff, facts: EncounterFacts, tier: Tier | int, owner_id: str, action: DecisionAction,
                   now: datetime) -> frozenset[Relation]:
    """Store layer: the exact role x relation x tier rule for this flag."""
    rel = relations(staff, facts, now, flag_owner_id=owner_id)
    if Relation.CARE_TEAM_MEMBER not in rel:
        raise ApiError(ErrorCode.NOT_FOUND)
    if not permissions.is_allowed(permissions.DECISION_PERMISSION[action], staff.role, rel, tier):
        raise ApiError(ErrorCode.FORBIDDEN_ROLE)
    return rel


def could_decide(staff: Staff, facts: EncounterFacts, action: DecisionAction, now: datetime) -> None:
    """Route layer, before any flag is loaded: refuse roles that may take this action on NO flag here."""
    rel = relations(staff, facts, now)
    if Relation.CARE_TEAM_MEMBER not in rel:
        raise ApiError(ErrorCode.NOT_FOUND)
    best = rel | {Relation.FLAG_OWNER}
    if not any(permissions.is_allowed(permissions.DECISION_PERMISSION[action], staff.role, best, t) for t in Tier):
        raise ApiError(ErrorCode.FORBIDDEN_ROLE)


# --- FastAPI dependencies (route layer) ------------------------------------------------

#: The action each encounter-scoped route requires at the route layer.
ROUTE_ACTIONS: dict[tuple[str, str], PermissionAction] = {
    ("GET", R.ENCOUNTER): A.READ_ENCOUNTER,
    ("POST", R.SOURCES): A.ADD_SOURCE,
    ("POST", R.SOURCES_PDF): A.ADD_SOURCE,
    ("GET", R.SOURCE_TEXT): A.READ_ENCOUNTER,
    ("POST", R.CHECK_RUNS): A.RUN_CHECKS,
    ("GET", R.CHECK_RUN_LATEST): A.READ_ENCOUNTER,
    ("GET", R.FLAGS): A.READ_ENCOUNTER,
    ("GET", R.FLAG): A.READ_ENCOUNTER,
    ("POST", R.FLAG_DECISIONS): A.READ_ENCOUNTER,  # + could_decide() in the route, + check_decision() in the store
    ("GET", R.BUBBLES): A.READ_ENCOUNTER,
    ("GET", R.CLOSURE): A.READ_ENCOUNTER,
    ("POST", R.CLOSURE): A.CLOSE_ENCOUNTER,
    ("GET", R.GLANCE): A.READ_ENCOUNTER,
    ("GET", R.SUMMARY): A.VIEW_SUMMARY,
    ("POST", R.DOCUMENT_TOKEN): A.VIEW_DOCUMENT,
    ("POST", R.FEEDBACK): A.RECORD_FEEDBACK,
}


def current_staff(request: Request, ng_session: str | None = Cookie(default=None)) -> Staff:
    staff = request.app.state.store.staff_for_session(ng_session)
    request_bag(request)["actor_id"] = staff.staff_id
    return staff


def auth_context(request: Request, staff: Staff = Depends(current_staff),
                 x_workspace_token: str | None = Header(default=None)) -> AuthContext:
    ctx = request.app.state.store.resolve_workspace(staff, x_workspace_token)
    request_bag(request)["workspace_hash"] = ctx.workspace_hash
    return ctx


def _deny(request: Request, ctx: AuthContext, encounter_id: str | None, code: ErrorCode) -> None:
    outcome = AuditOutcome.NOT_FOUND if code is ErrorCode.NOT_FOUND else AuditOutcome.DENIED
    request.app.state.audit.record(AuditAction.ACCESS_DENIED, AuditTargetType.ENCOUNTER, outcome, actor=ctx.staff,
                                   target_id=encounter_id)  # only ever a KNOWN encounter id, never URL input


def encounter_route_guard(request: Request, encounter_id: str, ctx: AuthContext = Depends(auth_context)) -> AuthContext:
    """ROUTE-layer scope + role check. Data path: the seed care-team directory (app.state.directory)."""
    action = ROUTE_ACTIONS[(request.method, request.scope["route"].path)]
    facts = request.app.state.directory.get(encounter_id)
    if facts is None:
        _deny(request, ctx, None, ErrorCode.NOT_FOUND)
        raise ApiError(ErrorCode.NOT_FOUND)
    try:
        check_encounter_action(ctx.staff, facts, action, utcnow())
    except ApiError as exc:
        _deny(request, ctx, encounter_id, exc.code)
        raise
    return ctx


def decision_route_check(request: Request, ctx: AuthContext, encounter_id: str, action: DecisionAction) -> None:
    facts = request.app.state.directory[encounter_id]  # guard already proved it exists
    try:
        could_decide(ctx.staff, facts, action, utcnow())
    except ApiError as exc:
        _deny(request, ctx, encounter_id, exc.code)
        raise


def require_aggregate_viewer(staff: Staff = Depends(current_staff)) -> Staff:
    """For B4's aggregate route: aggregate roles only; no encounter scope, no workspace."""
    if not permissions.is_allowed(A.VIEW_AGGREGATE, staff.role, frozenset()):
        raise ApiError(ErrorCode.FORBIDDEN_ROLE)
    return staff
