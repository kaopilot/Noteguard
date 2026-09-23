"""Deterministic identifier redaction with a source-to-redacted offset map (B2; Section 10.4).

Identifier patterns (NRIC/FIN, MRN, SG phone, email), the known-name pass and the interval-union
overlap rule are adapted from care-core backend/app/services/redaction.py (MIT License;
Copyright (c) 2019 Sebastián Ramírez; Copyright (c) 2026 Nightingale contributors; see
THIRD_PARTY_NOTICES.md). Changes: no NFC normalisation before matching (it would move offsets
off the ORIGINAL text), no Presidio/NLP model, spans reported as a RedactionReport with an offset
map, honorific-name / postal-code / date-of-birth patterns added, and a residual scan that also
refuses unknown long digit runs (fail closed).

Redaction is risk reduction, not permission: it exists only on the path to an external service.
Pure: the input is never modified or stored; the report carries the original's hash, not its text.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from noteguard.contracts import ids
from noteguard.contracts.egress import RedactionKind, RedactionReport, RedactionSpan

REDACTOR_VERSION = "noteguard-redact@1"
K = RedactionKind

# --- ported from care-core redaction.py (MIT) ---
NRIC_FIN = re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE)
MRN = re.compile(r"\bMRN[\s:#-]*[A-Z0-9-]{5,20}\b", re.IGNORECASE)
SG_PHONE = re.compile(r"(?<!\d)(?:\+65[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?!\d)")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
# --- added for Noteguard ---
HONORIFIC_NAME = re.compile(
    r"\b(?:Dr|Mr|Mrs|Ms|Mdm|Miss|Prof|Nurse|Sister|Pharmacist|Physio|SW|Clerk)\.? +[A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,2}\b")
SG_POSTAL = re.compile(r"\bSingapore\s+\d{6}\b")
DATE_OF_BIRTH = re.compile(r"\b(?:DOB|D\.O\.B\.?|date of birth)[\s:]*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", re.IGNORECASE)
#: Residual-only: an unrecognised long digit run may be an identifier we have no pattern for.
LONG_DIGITS = re.compile(r"(?<!\d)\d{7,}(?!\d)")

PATTERNS: tuple[tuple[RedactionKind, re.Pattern[str]], ...] = (
    (K.NRIC_FIN, NRIC_FIN), (K.MRN, MRN), (K.PHONE, SG_PHONE), (K.EMAIL, EMAIL),
    (K.DATE_OF_BIRTH, DATE_OF_BIRTH), (K.ADDRESS, SG_POSTAL), (K.PERSON_NAME, HONORIFIC_NAME),
)


@dataclass(frozen=True)
class _Hit:
    kind: RedactionKind
    start: int
    end: int


def _name_pattern(name: str) -> re.Pattern[str] | None:
    name = name.strip()
    if len(name) < 2:
        return None
    # Multi-word roster names match case-insensitively; single words only as written, so a roster
    # surname never redacts an ordinary word ("Tan" the person vs "tan-coloured" the sputum).
    flags = re.IGNORECASE if " " in name else 0
    return re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", flags)


class DeterministicRedactor:
    """Implements contracts.egress.Redactor."""

    def __init__(self, known_names: Iterable[str] = ()) -> None:
        self._names = tuple(p for p in map(_name_pattern, known_names) if p is not None)

    def _hits(self, text: str) -> list[_Hit]:
        out = [_Hit(K.PERSON_NAME, m.start(), m.end()) for p in self._names for m in p.finditer(text)]
        for kind, pattern in PATTERNS:
            out.extend(_Hit(kind, m.start(), m.end()) for m in pattern.finditer(text))
        return out

    @staticmethod
    def _non_overlapping(hits: Sequence[_Hit], n: int) -> list[_Hit]:
        """care-core rule: crossing spans ("Mary Ann" / "Ann Lee") expand to their union, so no
        fragment of an identifier is left outside a token."""
        valid = sorted((h for h in hits if 0 <= h.start < h.end <= n), key=lambda h: (h.start, -(h.end - h.start)))
        out: list[_Hit] = []
        for h in valid:
            if out and h.start < out[-1].end:
                if h.end > out[-1].end:
                    out[-1] = _Hit(out[-1].kind, out[-1].start, h.end)
                continue
            out.append(h)
        return out

    def _residuals(self, redacted: str) -> bool:
        return bool(self._hits(redacted)) or bool(LONG_DIGITS.search(redacted))

    def redact(self, text: str) -> RedactionReport:
        original_sha = ids.sha256_hex(text)
        try:
            chunks: list[str] = []
            spans: list[RedactionSpan] = []
            counts: Counter[RedactionKind] = Counter()
            cursor = pos = 0
            for h in self._non_overlapping(self._hits(text), len(text)):
                chunks.append(text[cursor:h.start])
                pos += h.start - cursor
                counts[h.kind] += 1
                token = f"[{h.kind.value.upper()}_{counts[h.kind]}]"
                spans.append(RedactionSpan(kind=h.kind, original_start=h.start, original_end=h.end,
                                           redacted_start=pos, redacted_end=pos + len(token), token=token))
                chunks.append(token)
                pos += len(token)
                cursor = h.end
            chunks.append(text[cursor:])
            redacted = "".join(chunks)
            residual_ok = not self._residuals(redacted)
        except Exception:  # noqa: BLE001 - fail closed; nothing about the input is logged or returned
            return RedactionReport(redactor_version=REDACTOR_VERSION, original_sha256=original_sha, redacted_text="",
                                   redacted_sha256=ids.sha256_hex(""), spans=(), residual_scan_passed=False,
                                   remote_egress_allowed=False, status="failed", error_code="redaction_error")
        status = "failed" if not residual_ok else ("redacted" if spans else "nothing_to_redact")
        return RedactionReport(redactor_version=REDACTOR_VERSION, original_sha256=original_sha, redacted_text=redacted,
                               redacted_sha256=ids.sha256_hex(redacted), spans=tuple(spans),
                               residual_scan_passed=residual_ok, remote_egress_allowed=residual_ok, status=status,
                               error_code=None if residual_ok else "residual_identifier")
