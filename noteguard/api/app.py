"""FastAPI application factory (B2 owns this file after CP0).

B0 state: the app serves the STUB routes (golden fixtures). ``app.state.is_stub`` is
True and every response carries X-Noteguard-Stub: 1. B2-owned tests refuse to run
against the stub (tests/conftest.py), so they fail "not implemented" until B2 lands.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from noteguard.contracts.routes import STUB_HEADER
from noteguard.contracts.types import CONTRACT_VERSION


def create_app() -> FastAPI:
    from noteguard.api.routes import stub

    app = FastAPI(title="Noteguard API (B0 stub)", version=CONTRACT_VERSION,
                  docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.is_stub = True
    app.include_router(stub.router)
    stub.install_error_handlers(app)

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        response.headers[STUB_HEADER] = "1"
        response.headers["Cache-Control"] = "private, no-store"
        return response

    return app


app = create_app()
