"""Structured, ALLOWLISTED logging (B2; L8, Section 10.3).

One logger ("noteguard"), one JSON record per event, and every record goes through
``contracts.log_allowlist.sanitize``: unknown keys and values of the wrong kind are DROPPED,
never masked. There is no code path that logs note text, rationale text, PDF bytes, raw URLs,
query strings, headers or request bodies.

Process-level hygiene (``configure_process_logging``): the uvicorn access log is disabled
(it prints raw paths and query strings) and third-party loggers that can carry raw URLs, form
data or PDF text at DEBUG/INFO are capped at WARNING. The request log carries the route
TEMPLATE, never the path. Known limit: a future dependency that logs content at WARNING or
above would bypass the cap; the marker test (test_marker_never_logged_or_echoed) is the guard.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from starlette.requests import Request
from starlette.routing import Match

from noteguard.contracts import ids
from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.log_allowlist import LogEvent, LogLevel, sanitize

from .errors import error_response

LOGGER_NAME = "noteguard"
_log = logging.getLogger(LOGGER_NAME)
_PY_LEVEL = {LogLevel.DEBUG: logging.DEBUG, LogLevel.INFO: logging.INFO,
             LogLevel.WARNING: logging.WARNING, LogLevel.ERROR: logging.ERROR}

#: Third-party loggers that may carry raw URLs (httpx logs every request URL at INFO),
#: multipart form data or PDF text fragments (pdfminer at DEBUG). Capped at WARNING.
QUIET_LOGGERS = ("httpx", "httpcore", "pdfminer", "pdfplumber", "multipart", "python_multipart", "PIL")

#: Scope key for per-request log context set by the auth dependencies (actor, workspace hash).
SCOPE_KEY = "noteguard"


class _StderrHandler(logging.StreamHandler):
    """Writes to the CURRENT sys.stderr at emit time (never a stale captured stream)."""

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, value) -> None:  # StreamHandler.__init__ assigns; ignore it
        pass


def configure_process_logging() -> None:
    access = logging.getLogger("uvicorn.access")
    access.disabled = True
    access.propagate = False
    access.handlers.clear()
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    if not any(isinstance(h, _StderrHandler) for h in _log.handlers):
        _log.addHandler(_StderrHandler())
    _log.setLevel(logging.INFO)


def _plain(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def log_event(event: LogEvent, level: LogLevel = LogLevel.INFO, **fields: Any) -> dict[str, Any]:
    """Emit one allowlisted JSON record. Returns what was actually logged (post-sanitize)."""
    record = dict(event=event.value, level=level.value, at=_plain(datetime.now(timezone.utc)))
    record.update({k: _plain(v) for k, v in fields.items()})
    clean = sanitize(record)
    _log.log(_PY_LEVEL[level], json.dumps(clean, sort_keys=True, ensure_ascii=True))
    return clean


def request_bag(request: Request) -> dict[str, Any]:
    return request.scope.setdefault(SCOPE_KEY, {})


def _route_template(request: Request) -> str | None:
    route = request.scope.get("route")
    if route is not None:
        return getattr(route, "path", None)
    for r in request.app.router.routes:
        match, _ = r.matches(request.scope)
        if match is Match.FULL:
            return getattr(r, "path", None)
    return None


async def request_middleware(request: Request, call_next):
    """Headers on EVERY response (incl. errors) + one route-template request log line.
    Unhandled exceptions end here as a bare 500 internal_error: no traceback, no locals,
    and nothing re-raised to the server's error log."""
    started = time.perf_counter()
    bag = request_bag(request)
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 - deliberate: nothing about the exception is logged
        bag["error_code"] = ErrorCode.INTERNAL_ERROR
        response = error_response(ErrorCode.INTERNAL_ERROR)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    log_event(LogEvent.HTTP_REQUEST if response.status_code < 500 else LogEvent.ERROR,
              LogLevel.INFO if response.status_code < 500 else LogLevel.ERROR,
              request_id=ids.new_id(), route_template=_route_template(request), method=request.method,
              status_code=response.status_code, duration_ms=round((time.perf_counter() - started) * 1000, 3),
              actor_id=bag.get("actor_id"), workspace_hash=bag.get("workspace_hash"), error_code=bag.get("error_code"))
    return response
