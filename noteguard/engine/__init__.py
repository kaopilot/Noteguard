"""Noteguard check engine (B1 owns this package).

B0 scaffold: get_engine() raises NotImplementedError until B1 lands the real engine,
so every engine-level test fails with "not implemented" rather than an import error.
The engine must stay pure: no FastAPI, no file or network access, no logging of content.
"""

from __future__ import annotations

from noteguard.contracts.engine_api import EngineAPI


def get_engine() -> EngineAPI:
    raise NotImplementedError("B1: noteguard.engine not implemented yet (B0 scaffold)")
