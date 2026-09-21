"""Forbidden phrasings (Section 8.8, 13, 17). One list, used by the lint test and by
any runtime validator (API responses, templates, AI output).

"Not documented in the supplied sources" is allowed. "Did not happen" is not.
"""

from __future__ import annotations

import re

#: Absence-as-event claims: forbidden EVERYWHERE (data, API, UI, summary, AI output).
ABSENCE_EVENT_PHRASES: tuple[str, ...] = (
    "did not happen",
    "didn't happen",
    "did not occur",
    "was not done",
    "was not performed",
    "was not given",
    "was never given",
    "was not administered",
    "never received",
    "never happened",
    "no ecg was",
    "not carried out",
)

#: Verdict tone: forbidden in UI copy, templates, flag reasons, questions and AI output.
VERDICT_TONE_PHRASES: tuple[str, ...] = (
    "missed",
    "failed to",
    "negligent",
    "error by",
)

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text.replace("\u2019", "'")).strip().lower()


def find_forbidden(text: str, *, include_tone: bool = True) -> str | None:
    """Return the first forbidden phrase found in ``text`` (case/whitespace-insensitive)."""
    t = _norm(text)
    phrases = ABSENCE_EVENT_PHRASES + (VERDICT_TONE_PHRASES if include_tone else ())
    for p in phrases:
        if re.search(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])", t):
            return p
    return None
