"""Noteguard check engine (B1 owns this package).

``get_engine()`` returns the pure, deterministic engine (engine.py). It imports no web,
file, network, clock or logging module and never logs content (test_engine_is_pure).
"""

from __future__ import annotations

from noteguard.contracts.engine_api import EngineAPI

from .engine import Engine


def get_engine() -> EngineAPI:
    return Engine()
