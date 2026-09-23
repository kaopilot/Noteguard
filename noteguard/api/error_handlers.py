"""Error handlers (B2; L20). Every error body is {"error_code": ...} only; nothing from the
request (body, path, query, headers) is echoed, and no traceback or locals are rendered."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from noteguard.contracts import routes as R
from noteguard.contracts.errors import ErrorCode

from .errors import ApiError, error_response
from .logs import request_bag

_HTTP_CODES = {401: ErrorCode.UNAUTHENTICATED, 403: ErrorCode.FORBIDDEN_ROLE, 404: ErrorCode.NOT_FOUND,
               405: ErrorCode.NOT_FOUND, 413: ErrorCode.PDF_TOO_LARGE, 422: ErrorCode.VALIDATION_FAILED}


def _is_bulk(request: Request, exc: RequestValidationError) -> bool:
    """A list body on the decision route is a bulk attempt (L15): say so, without echoing it."""
    route = request.scope.get("route")
    if getattr(route, "path", None) != R.FLAG_DECISIONS:
        return False
    return any(e.get("loc") == ("body",) and isinstance(e.get("input"), list) for e in exc.errors())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        request_bag(request)["error_code"] = exc.code
        return error_response(exc.code, exc.stale)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        code = ErrorCode.BULK_NOT_SUPPORTED if _is_bulk(request, exc) else ErrorCode.VALIDATION_FAILED
        request_bag(request)["error_code"] = code
        return error_response(code)  # never FastAPI's default body, which echoes the input

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, ErrorCode.VALIDATION_FAILED if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR)
        request_bag(request)["error_code"] = code
        return error_response(code, status=exc.status_code)
