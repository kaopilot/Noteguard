"""Error codes (frozen, B0). Error bodies are {"error_code": "<code>"} only (L20);
the one extension is the 409 StaleRevision body in types.py."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    UNAUTHENTICATED = "unauthenticated"  # 401
    NOT_FOUND = "not_found"  # 404; ALSO used for out-of-scope encounters (no existence leak)
    FORBIDDEN_ROLE = "forbidden_role"  # 403; in scope but role/relation lacks the action
    VALIDATION_FAILED = "validation_failed"  # 422; never echoes input
    INVALID_TRANSITION = "invalid_transition"  # 409
    STALE_REVISION = "stale_revision"  # 409 with StaleRevision body
    REASON_CODE_REQUIRED = "reason_code_required"  # 422
    REASON_CODE_NOT_ALLOWED = "reason_code_not_allowed"  # 422
    RATIONALE_REQUIRED = "rationale_required"  # 422
    ADJUDICATION_REQUIRED = "adjudication_required"  # 422
    REASSIGN_TARGET_INVALID = "reassign_target_invalid"  # 422
    BULK_NOT_SUPPORTED = "bulk_not_supported"  # 422
    TIER1_CANNOT_BE_DEFERRED = "tier1_cannot_be_deferred"  # 422
    CLOSURE_BLOCKED = "closure_blocked"  # 409
    WORKSPACE_REQUIRED = "workspace_required"  # 401
    WORKSPACE_EXPIRED = "workspace_expired"  # 410
    PDF_TOO_LARGE = "pdf_too_large"  # 413
    PDF_TOO_MANY_PAGES = "pdf_too_many_pages"  # 422
    PDF_NOT_A_PDF = "pdf_not_a_pdf"  # 415
    PDF_EXTRACTION_TIMEOUT = "pdf_extraction_timeout"  # 422 (source retained, status failed)
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"  # 409
    DOCUMENT_TOKEN_INVALID = "document_token_invalid"  # 404
    RULESET_UNAPPROVED = "ruleset_unapproved"  # 503 at startup
    AI_DISABLED = "ai_disabled"  # 409; the feature says "disabled", never fakes a result
    AI_UNAVAILABLE = "ai_unavailable"  # 503; caller falls back to rule text
    NOT_IMPLEMENTED = "not_implemented"  # 501; stub routes before a lane lands
    RATE_LIMITED = "rate_limited"  # 429 (known gap: not implemented in the demonstrator)
    INTERNAL_ERROR = "internal_error"  # 500; no traceback, no locals


HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FORBIDDEN_ROLE: 403,
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.INVALID_TRANSITION: 409,
    ErrorCode.STALE_REVISION: 409,
    ErrorCode.REASON_CODE_REQUIRED: 422,
    ErrorCode.REASON_CODE_NOT_ALLOWED: 422,
    ErrorCode.RATIONALE_REQUIRED: 422,
    ErrorCode.ADJUDICATION_REQUIRED: 422,
    ErrorCode.REASSIGN_TARGET_INVALID: 422,
    ErrorCode.BULK_NOT_SUPPORTED: 422,
    ErrorCode.TIER1_CANNOT_BE_DEFERRED: 422,
    ErrorCode.CLOSURE_BLOCKED: 409,
    ErrorCode.WORKSPACE_REQUIRED: 401,
    ErrorCode.WORKSPACE_EXPIRED: 410,
    ErrorCode.PDF_TOO_LARGE: 413,
    ErrorCode.PDF_TOO_MANY_PAGES: 422,
    ErrorCode.PDF_NOT_A_PDF: 415,
    ErrorCode.PDF_EXTRACTION_TIMEOUT: 422,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.DOCUMENT_TOKEN_INVALID: 404,
    ErrorCode.RULESET_UNAPPROVED: 503,
    ErrorCode.AI_DISABLED: 409,
    ErrorCode.AI_UNAVAILABLE: 503,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
}
