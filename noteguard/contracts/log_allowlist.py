"""Log and audit key ALLOWLIST (frozen, B0; L8). Unknown keys are DROPPED, not masked.
Values must match their declared kind or the key is dropped. No free text, ever."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from .errors import ErrorCode
from .routes import ROUTE_TEMPLATES
from .types import (
    AIDraftStatus,
    AuditAction,
    AuditOutcome,
    AuditTargetType,
    DecisionAction,
    ExtractionStatus,
    FlagState,
    ReasonCode,
    Role,
    RuleId,
)


class LogEvent(str, Enum):
    HTTP_REQUEST = "http_request"
    AUDIT = "audit"
    CHECK_RUN = "check_run"
    INTAKE = "intake"
    DECISION = "decision"
    ERROR = "error"
    STARTUP = "startup"
    AI = "ai"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_STABLE = re.compile(r"^(flg|bbl)_[0-9a-f]{24}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CHECK_VERSION = re.compile(r"^ruleset@[A-Za-z0-9.\-]+;rule@[A-Z]+-\d{3}\.\d+;registry@[A-Za-z0-9.\-]+$")
_VERSION_LABEL = re.compile(r"^v\d+(\.\d+)*$")


def _enum(e: type[Enum]) -> Callable[[Any], bool]:
    values = {m.value for m in e}
    return lambda v: isinstance(v, (str, int)) and not isinstance(v, bool) and v in values


def _opaque_id(v: Any) -> bool:
    return isinstance(v, str) and bool(_UUID.match(v) or _STABLE.match(v))


def _flag_id(v: Any) -> bool:
    return isinstance(v, str) and bool(_STABLE.match(v)) and v.startswith("flg_")


def _hex64(v: Any) -> bool:
    return isinstance(v, str) and bool(_HEX64.match(v))


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _timestamp(v: Any) -> bool:
    if isinstance(v, datetime):
        return v.tzinfo is not None
    if not isinstance(v, str) or len(v) > 40:
        return False
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _route_template(v: Any) -> bool:
    return isinstance(v, str) and v in ROUTE_TEMPLATES


def _tier(v: Any) -> bool:
    return _int(v) and v in (1, 2, 3)


def _check_version(v: Any) -> bool:
    return isinstance(v, str) and bool(_CHECK_VERSION.match(v))


def _version_label(v: Any) -> bool:
    return isinstance(v, str) and bool(_VERSION_LABEL.match(v))


def _hex64_list(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and len(v) <= 16 and all(_hex64(x) for x in v)


#: key -> validator. THE allowlist. Nothing else may appear in a log record or audit event.
LOG_KEYS: dict[str, Callable[[Any], bool]] = {
    "event": _enum(LogEvent),
    "level": _enum(LogLevel),
    "at": _timestamp,
    "request_id": _opaque_id,
    "route_template": _route_template,
    "method": _enum(HttpMethod),
    "status_code": _int,
    "duration_ms": _number,
    "actor_id": _opaque_id,
    "role": _enum(Role),
    "action": _enum(AuditAction),
    "target_type": _enum(AuditTargetType),
    "target_id": _opaque_id,
    "outcome": _enum(AuditOutcome),
    "error_code": _enum(ErrorCode),
    "encounter_id": _opaque_id,
    "flag_id": _flag_id,
    "rule_id": _enum(RuleId),
    "tier": _tier,
    "state": _enum(FlagState),
    "decision_action": _enum(DecisionAction),
    "reason_code": _enum(ReasonCode),
    "source_version_id": _opaque_id,
    "extraction_status": _enum(ExtractionStatus),
    "run_id": _opaque_id,
    "event_id": _opaque_id,
    "check_version": _check_version,
    "ruleset_version": _version_label,
    "registry_version": _version_label,
    "count": _int,
    "flags_raised": _int,
    "sources_in_scope": _int,
    "sha256": _hex64,
    "hashes": _hex64_list,
    "prev_event_hash": _hex64,
    "event_hash": _hex64,
    "workspace_hash": _hex64,  # hash of the workspace token; the token itself is never logged
    "ai_status": _enum(AIDraftStatus),
}

#: Keys an AuditEvent may carry (subset of LOG_KEYS; see types.AuditEvent).
AUDIT_KEYS: frozenset[str] = frozenset({
    "event_id", "at", "actor_id", "role", "action", "target_type", "target_id",
    "outcome", "hashes", "prev_event_hash", "event_hash",
})


def is_allowed(key: str, value: Any) -> bool:
    check = LOG_KEYS.get(key)
    return check is not None and value is not None and check(value)


def sanitize(record: dict[str, Any]) -> dict[str, Any]:
    """Drop every key that is not allowlisted or whose value fails its kind."""
    return {k: v for k, v in record.items() if is_allowed(k, v)}
