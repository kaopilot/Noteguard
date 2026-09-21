"""Flag state machine and the closure-blocking predicate (frozen, B0).

Humans move flags with DecisionActions. The engine moves flags only with
EngineTransitions, and NEVER into dismissed or resolved (no auto-closure, ever).
"""

from __future__ import annotations

from .types import DecisionAction, EngineTransition, FlagState, Tier

S = FlagState

#: Human decision transitions: action -> {from_state: to_state}.
DECISION_TRANSITIONS: dict[DecisionAction, dict[FlagState, FlagState]] = {
    DecisionAction.ACCEPT: {S.OPEN: S.ACCEPTED, S.EDITED: S.ACCEPTED},
    DecisionAction.EDIT: {S.OPEN: S.EDITED, S.ACCEPTED: S.EDITED, S.EDITED: S.EDITED},
    # Reassign changes the owner; the new owner has not accepted yet -> edited.
    DecisionAction.REASSIGN: {S.OPEN: S.EDITED, S.ACCEPTED: S.EDITED, S.EDITED: S.EDITED},
    # Staff prepare: sets ready_for_clinician, state unchanged.
    DecisionAction.MARK_READY_FOR_CLINICIAN: {S.OPEN: S.OPEN, S.ACCEPTED: S.ACCEPTED, S.EDITED: S.EDITED},
    DecisionAction.DISMISS: {S.OPEN: S.DISMISSED, S.ACCEPTED: S.DISMISSED, S.EDITED: S.DISMISSED, S.SUPERSEDED: S.DISMISSED},
    # Resolving a superseded flag is how a clinician CONFIRMS a documented response.
    DecisionAction.RESOLVE: {S.OPEN: S.RESOLVED, S.ACCEPTED: S.RESOLVED, S.EDITED: S.RESOLVED, S.SUPERSEDED: S.RESOLVED},
}

#: Engine transitions: transition -> {from_state (None = not yet raised): to_state}.
ENGINE_TRANSITIONS: dict[EngineTransition, dict[FlagState | None, FlagState]] = {
    EngineTransition.RAISE: {None: S.OPEN},
    # A later documented response / evidence no longer present, AFTER a human could see it.
    EngineTransition.SUPERSEDE: {S.OPEN: S.SUPERSEDED, S.ACCEPTED: S.SUPERSEDED, S.EDITED: S.SUPERSEDED},
    # New contradicting evidence from a different source (L2), or a suppression that vanished.
    EngineTransition.REOPEN: {S.DISMISSED: S.OPEN, S.RESOLVED: S.OPEN, S.SUPERSEDED: S.OPEN},
}

#: States the engine may never produce. Asserted by test_contract_states.
ENGINE_FORBIDDEN_TARGETS = frozenset({S.DISMISSED, S.RESOLVED, S.ACCEPTED, S.EDITED})

#: Decisions that require a reason code.
REASON_REQUIRED = frozenset({DecisionAction.DISMISS, DecisionAction.RESOLVE})
#: Decisions that require free-text rationale (held in memory only).
RATIONALE_REQUIRED = frozenset({DecisionAction.EDIT, DecisionAction.REASSIGN})


class InvalidTransition(ValueError):
    """Raised for a transition not in the tables above."""


def decision_target(action: DecisionAction, current: FlagState) -> FlagState:
    try:
        return DECISION_TRANSITIONS[action][current]
    except KeyError as exc:
        raise InvalidTransition(f"{action.value} not allowed from {current.value}") from exc


def engine_target(transition: EngineTransition, current: FlagState | None) -> FlagState:
    try:
        return ENGINE_TRANSITIONS[transition][current]
    except KeyError as exc:
        raise InvalidTransition(f"engine {transition.value} not allowed from {current}") from exc


def blocks_closure(tier: Tier | int, state: FlagState) -> bool:
    """OPEN-6 default: an accepted Tier 1 still blocks. Only resolved, dismissed
    (clinician, with reason code) or clinician-confirmed superseded (= resolve)
    unblock. An unconfirmed superseded Tier 1 still blocks (Section 8.5)."""
    return int(tier) == 1 and state in {S.OPEN, S.ACCEPTED, S.EDITED, S.SUPERSEDED}


def is_unresolved(tier: Tier | int, state: FlagState) -> bool:
    """Counts toward open priorities, the glance strip and the summary."""
    if state in {S.OPEN, S.ACCEPTED, S.EDITED}:
        return True
    return int(tier) == 1 and state == S.SUPERSEDED
