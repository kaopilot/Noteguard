"""Lane gates (B0). Every entry point into another lane's code goes through here, so a
lane that has not landed fails with NotImplementedError ("not implemented"), never with
an ImportError or a green result from a stub."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def not_implemented(lane: str, what: str) -> None:
    raise NotImplementedError(f"{lane}: {what}")


def engine():
    """The REAL engine (B1). Raises NotImplementedError until B1 lands."""
    from noteguard.engine import get_engine

    eng = get_engine()
    if getattr(eng, "is_stub", False):
        not_implemented("B1", "the stub engine is behind noteguard.engine.get_engine()")
    return eng


def real_app():
    """The REAL API app (B2). Raises NotImplementedError while the B0 stub is in place."""
    from noteguard.api.app import create_app

    app = create_app()
    if getattr(app.state, "is_stub", False):
        not_implemented("B2", "stub API still in the request path")
    return app


def any_app():
    """Whatever app is in place (stub before B2, real after). For contract/count tests."""
    from noteguard.api.app import create_app

    return create_app()


def client(app) -> TestClient:
    return TestClient(app)


def lane_module(dotted: str, lane: str):
    """Import another lane's module; a missing module means 'not implemented', not an error."""
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as exc:
        if exc.name and dotted.startswith(exc.name):
            not_implemented(lane, f"module {dotted} does not exist yet")
        raise
