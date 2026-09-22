"""Hash-chained, append-only audit stream (B2; Section 7 AuditEvent, 10.3).

Allowlisted fields only (contracts/log_allowlist.AUDIT_KEYS): ids, enums, hashes, timestamps.
No clinical content, no request input. Each event links to the previous one:
event_hash = sha256(prev_event_hash + canonical(fields without event_hash)) (contracts/ids.py),
so editing, dropping or reordering any event breaks ``verify_chain``.

Kept separate from content provenance (Evidence -> SourceVersion), which lives on the flags.
Declared limit: process memory only (single-process demonstrator); production appends to a
WORM store and anchors the chain head externally.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from noteguard.contracts import ids
from noteguard.contracts.log_allowlist import LogEvent
from noteguard.contracts.types import AuditAction, AuditEvent, AuditOutcome, AuditTargetType, Staff

from .logs import log_event
from .settings import utcnow


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()

    def record(self, action: AuditAction, target_type: AuditTargetType, outcome: AuditOutcome, *,
               actor: Staff | None = None, target_id: str | None = None, hashes: Iterable[str] = ()) -> AuditEvent:
        with self._lock:
            prev = self._events[-1].event_hash if self._events else ids.GENESIS_AUDIT_HASH
            draft = AuditEvent(event_id=ids.new_id(), at=utcnow(), actor_id=actor.staff_id if actor else None,
                               role=actor.role if actor else None, action=action, target_type=target_type,
                               target_id=target_id, outcome=outcome, hashes=tuple(hashes), prev_event_hash=prev,
                               event_hash=ids.GENESIS_AUDIT_HASH)
            fields = draft.model_dump(mode="json", exclude={"event_hash"})
            event = AuditEvent.model_validate(dict(fields, event_hash=ids.audit_event_hash(prev, fields)))
            self._events.append(event)
        log_event(LogEvent.AUDIT, **event.model_dump(mode="json"))
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)


def verify_chain(events: Iterable[AuditEvent]) -> bool:
    prev = ids.GENESIS_AUDIT_HASH
    for e in events:
        fields = e.model_dump(mode="json", exclude={"event_hash"})
        if e.prev_event_hash != prev or ids.audit_event_hash(prev, fields) != e.event_hash:
            return False
        prev = e.event_hash
    return True
