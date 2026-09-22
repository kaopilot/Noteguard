"""The one way to prepare text for an external service (B2 -> B4 seam; Section 9, 10.4).

Redacts, then mints a ``QualifiedRedactedText`` (contracts/egress.py). Fails closed: if redaction
errors or the residual scan finds an identifier, ValueError is raised and no payload exists, so
the provider call cannot happen. Providers must still call ``payload.assert_qualified()``.
"""

from __future__ import annotations

from noteguard.contracts.egress import QualifiedRedactedText, Redactor


def prepare_egress(text: str, *, redactor: Redactor) -> QualifiedRedactedText:
    return QualifiedRedactedText.from_report(redactor.redact(text))
