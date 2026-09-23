"""Redaction and egress gate (B2). ``get_redactor()`` per contracts/egress.py."""

from __future__ import annotations

from collections.abc import Iterable

from noteguard.contracts.egress import Redactor

from .egress import prepare_egress
from .redact import REDACTOR_VERSION, DeterministicRedactor


def get_redactor(known_names: Iterable[str] = ()) -> Redactor:
    """``known_names``: roster names to redact in addition to the patterns (e.g. the encounter's
    staff and patient names, supplied by the caller from the snapshot)."""
    return DeterministicRedactor(known_names)


__all__ = ["get_redactor", "prepare_egress", "REDACTOR_VERSION", "DeterministicRedactor"]
