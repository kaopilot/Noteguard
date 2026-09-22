"""Dose unit canonicalisation for DOSE-001 comparison ("0.5 g" == "500 mg").

Which strings are dose units is decided ONLY by ``registry.dose_units`` (L5). This module
holds arithmetic, not vocabulary: metric mass prefixes, and folding a plural or abbreviated
unit onto the singular form the registry also lists. A unit it cannot fold is compared as
written, so an unfamiliar unit can only make two regimens look different (flag), never the
same (pass). Proposed move into the registry schema: docs/contract_changes/CCR-01.md.
"""

from __future__ import annotations

# grams per unit, keyed by the unit's metric form
_MASS = {"g": 1.0, "mg": 1e-3, "mcg": 1e-6, "microgram": 1e-6, "micrograms": 1e-6}
_FOLD = {"tabs": "tablet", "tablets": "tablet", "units": "unit"}


def canonical(amount: float, unit: str) -> tuple[float, str]:
    """(amount, unit) with mass in mg and count units folded to one spelling."""
    u = unit.lower()
    if u in _MASS:
        return round(amount * _MASS[u] / _MASS["mg"], 6), "mg"
    return amount, _FOLD.get(u, u)


def fmt(amount: float) -> str:
    return f"{amount:g}"
