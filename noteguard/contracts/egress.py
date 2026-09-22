"""Redaction report and egress gate contract (frozen, B0). Seam between B2 (redaction,
provider boundary) and B4 (AI drafting): B2 implements the redactor and the gate, B4 may
send ONLY a QualifiedRedactedText to a model provider.

``QualifiedRedactedText`` is adapted from care-core
backend/app/services/egress.py (MIT License; Copyright (c) 2019 Sebastián Ramírez;
Copyright (c) 2026 Nightingale contributors). See THIRD_PARTY_NOTICES.md.
Changes: pydantic report model with an offset map; the report carries the original's
hash (never the original text).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from pydantic import Field, NonNegativeInt

from .types import Frozen, Sha256Hex


class RedactionKind(str, Enum):
    PERSON_NAME = "person_name"
    NRIC_FIN = "nric_fin"  # Singapore identity numbers
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    MRN = "mrn"
    OTHER_IDENTIFIER = "other_identifier"


class RedactionSpan(Frozen):
    """One replaced span. Offsets are code points into the ORIGINAL text (end exclusive)
    and into the redacted text, so evidence offsets can be mapped both ways."""

    kind: RedactionKind
    original_start: NonNegativeInt
    original_end: NonNegativeInt
    redacted_start: NonNegativeInt
    redacted_end: NonNegativeInt
    token: str = Field(pattern=r"^\[[A-Z_]+_\d+\]$")  # e.g. "[NRIC_FIN_1]"


class RedactionReport(Frozen):
    """Output of B2's redactor. Holds the redacted text and hashes, never the original."""

    redactor_version: str
    original_sha256: Sha256Hex
    redacted_text: str
    redacted_sha256: Sha256Hex
    spans: tuple[RedactionSpan, ...]
    residual_scan_passed: bool
    remote_egress_allowed: bool
    status: str  # "redacted" | "nothing_to_redact" | "failed"
    error_code: str | None = None


_QUALIFICATION_MARKER = object()


@dataclass(frozen=True, init=False)
class QualifiedRedactedText:
    """Opaque payload minted only from a passing RedactionReport. Providers accept nothing else."""

    text: str
    sha256: str
    redaction_status: str
    _qualification_marker: object = field(repr=False, compare=False)

    @classmethod
    def from_report(cls, report: RedactionReport) -> "QualifiedRedactedText":
        digest = hashlib.sha256(report.redacted_text.encode()).hexdigest()
        if (
            not report.remote_egress_allowed
            or not report.residual_scan_passed
            or report.error_code is not None
            or digest != report.redacted_sha256
        ):
            raise ValueError("REMOTE_TEXT_EGRESS_NOT_QUALIFIED")
        payload = object.__new__(cls)
        object.__setattr__(payload, "text", report.redacted_text)
        object.__setattr__(payload, "sha256", digest)
        object.__setattr__(payload, "redaction_status", report.status)
        object.__setattr__(payload, "_qualification_marker", _QUALIFICATION_MARKER)
        return payload

    def assert_qualified(self) -> None:
        """Revalidate provenance and integrity at the provider boundary."""
        digest = hashlib.sha256(self.text.encode()).hexdigest()
        if getattr(self, "_qualification_marker", None) is not _QUALIFICATION_MARKER or digest != self.sha256:
            raise ValueError("REMOTE_TEXT_EGRESS_NOT_QUALIFIED")


class Redactor(Protocol):
    """B2 implements it and exposes ``noteguard.redaction.get_redactor() -> Redactor``.
    Pure: returns a report, never mutates or stores the input."""

    def redact(self, text: str) -> RedactionReport: ...


class DraftingProvider(Protocol):
    """Model provider boundary (B4 calls, B2's gate guards). Must call payload.assert_qualified()
    first and honour the timeout; raises on timeout so the caller falls back to rule text."""

    def draft(self, payload: QualifiedRedactedText, *, timeout_s: float) -> str: ...
