"""The ONE seam between the API and the check engine (B2).

B2 builds against ``noteguard.engine_stub.StubEngine`` (golden inputs only; anything else raises
NotImplementedError, which the API reports as 501 not_implemented, never a plausible value).
I1 swaps in the real engine with ``create_app(engine=get_engine(), bundle_loader=<B4 approved
ruleset loader>)``. Tiers, owners, states and closure come from the engine and
contracts.states; the API never re-derives them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from noteguard.contracts.engine_api import EngineAPI
from noteguard.contracts.types import RulesetBundle
from noteguard.engine_stub import StubEngine


@dataclass(frozen=True)
class EngineSeam:
    engine: EngineAPI
    load_bundle: Callable[[], RulesetBundle | None]


def _stub_bundle() -> None:
    """The stub engine serves golden fixtures and never reads a ruleset bundle."""
    return None


def _bundle_not_wired() -> RulesetBundle:
    raise NotImplementedError("I1: pass the approved ruleset loader (B4) with the real engine")


def make_seam(engine: EngineAPI | None = None,
              bundle_loader: Callable[[], RulesetBundle | None] | None = None) -> EngineSeam:
    if engine is None:
        return EngineSeam(StubEngine(), bundle_loader or _stub_bundle)
    return EngineSeam(engine, bundle_loader or _bundle_not_wired)
