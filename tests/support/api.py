"""HTTP helpers for API-level tests (B0)."""

from __future__ import annotations

from noteguard.contracts import routes as R

from .builders import staff_id
from .golden import load

A1 = load("ENC-A1_1130")["encounter_id"]
B1 = load("ENC-B1_1600")["encounter_id"]
C1 = load("ENC-C1_1000")["encounter_id"]


def login(c, staff_key: str) -> dict:
    """Synthetic login + a fresh per-page-load workspace; returns request headers."""
    r = c.post(R.SESSION, json={"staff_id": staff_id(staff_key)})
    assert r.status_code == 200, r.status_code
    w = c.post(R.WORKSPACES)
    assert w.status_code == 200, w.status_code
    return {R.WORKSPACE_HEADER: w.json()["workspace_token"]}


def url(template: str, **kw) -> str:
    return template.format(**kw)


def run_cutoff(c, h: dict, encounter_id: str, scenario: str):
    return c.post(url(R.CHECK_RUNS, encounter_id=encounter_id), headers=h, json={"cutoff": load(scenario)["cutoff"]})
