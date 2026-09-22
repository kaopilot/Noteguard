"""API error type (B2). Bodies are {"error_code": ...} only (L20); the single extension is
the 409 StaleRevision body defined in contracts/types.py. Never carries input or content."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from noteguard.contracts.errors import HTTP_STATUS, ErrorCode
from noteguard.contracts.types import StaleRevision


class ApiError(Exception):
    """Raised by authz, the store and intake. Rendered by error_handlers.py."""

    def __init__(self, code: ErrorCode, stale: StaleRevision | None = None) -> None:
        super().__init__(code.value)
        self.code = code
        self.stale = stale


def error_response(code: ErrorCode, stale: StaleRevision | None = None, status: int | None = None) -> JSONResponse:
    body = stale.model_dump(mode="json") if stale is not None else {"error_code": code.value}
    return JSONResponse(body, status_code=status or HTTP_STATUS[code])
