"""FastAPI application factory (B2).

Real routes on exactly contracts.routes.ROUTE_TEMPLATES; ``app.state.is_stub`` is False.
SINGLE-PROCESS, IN-MEMORY demonstrator (declared): sessions, workspaces, audit chain and
document tokens live in this process only; run one worker. Production uses Postgres + RLS.

Configuration is code (``create_app(settings=Settings(...))``), never environment variables
(L12). The engine is called through one seam (engine_seam.py): the stub engine until I1, then
``create_app(engine=noteguard.engine.get_engine(), bundle_loader=api_bundle_loader())`` (B4's factory,
noteguard.governance.approval; CALL it: passing the factory itself hands the engine a function).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from noteguard.contracts.engine_api import EngineAPI
from noteguard.contracts.log_allowlist import LogEvent
from noteguard.contracts.types import CONTRACT_VERSION, RulesetBundle

from .audit import AuditLog
from .authz import EncounterFacts
from .engine_seam import make_seam
from .error_handlers import install_error_handlers
from .logs import configure_process_logging, log_event, request_middleware
from .seed import load_seed
from .settings import Settings
from .store import WorkspaceStore


def create_app(*, settings: Settings | None = None, engine: EngineAPI | None = None,
               bundle_loader: Callable[[], RulesetBundle | None] | None = None) -> FastAPI:
    from noteguard.api.routes import aggregate, core

    configure_process_logging()
    settings = settings or Settings()
    seed = load_seed()
    audit = AuditLog()
    app = FastAPI(title="Noteguard API", version=CONTRACT_VERSION, docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json")
    app.state.is_stub = False
    app.state.settings = settings
    app.state.audit = audit
    #: ROUTE-layer authz data path: the care-team directory, built once from the seed.
    app.state.directory = {s.encounter.encounter_id: EncounterFacts(s.encounter, s.memberships) for s in seed.snapshots}
    #: STORE-layer authz and all clinical content: the per-page-load workspace store.
    app.state.store = WorkspaceStore(settings=settings, seed=seed, audit=audit, seam=make_seam(engine, bundle_loader))
    app.include_router(core.router)
    app.include_router(aggregate.router)
    install_error_handlers(app)
    app.middleware("http")(request_middleware)
    log_event(LogEvent.STARTUP)
    return app


app = create_app()
