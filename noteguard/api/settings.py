"""Runtime settings (B2). Plain code constants passed to ``create_app(settings=...)``.

Nothing here is read from the environment: no security behaviour may change with an
environment flag (L12). Every key is read by the app and has a config-effect test that
changes it and observes the behaviour change (L11, tests/api/test_api_behaviour.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Settings:
    session_ttl_s: int = 8 * 3600  # identity cookie lifetime (server-side expiry too)
    workspace_ttl_s: int = 8 * 3600  # per-page-load workspace lifetime (Section 6.3)
    pdf_max_bytes: int = 10 * 1024 * 1024  # 413 pdf_too_large above this
    pdf_max_pages: int = 50  # 422 pdf_too_many_pages above this
    pdf_extraction_timeout_s: float = 10.0  # 422 pdf_extraction_timeout; source retained as failed
    document_token_ttl_s: int = 60  # short-lived, single-use document tokens


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
