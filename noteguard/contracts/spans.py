"""Statement spans (frozen, B0): the ONE definition of what an evidence span covers.

Golden fixtures compare evidence by exact offsets, so the engine, the goldens and the
UI must agree on span boundaries. Every Assertion.span and every non-gap Evidence
span is one of ``statement_spans(text)``. B1 imports this; it does not reimplement it.

Convention (offsets are Unicode code points into the ORIGINAL text, end exclusive):
1. Text is split into lines on "\\n".
2. A leading list marker ("1. ", "2) ", up to two digits) is not part of a statement.
3. Within a line, a statement ends at ".", "!" or "?" followed by whitespace or the end
   of the line. A terminator followed by anything else ("6.4", "?penicillin", '?"')
   does not split.
4. Leading/trailing whitespace is trimmed. A trailing "." or "!" is excluded from the
   span; a trailing "?" is kept (it carries uncertainty).
5. Empty statements are dropped.

Known limitation: abbreviations with a period followed by a space ("e.g. ") split a
statement. Recorded in docs/decisions/B0.md; change only by CCR.
"""

from __future__ import annotations

import re

_LIST_MARKER = re.compile(r"\d{1,2}[.)]\s+")
_TERMINATORS = ".!?"


def _emit(line: str, base: int, s: int, e: int, out: list[tuple[int, int]]) -> None:
    while s < e and line[s].isspace():
        s += 1
    while e > s and line[e - 1].isspace():
        e -= 1
    if e > s:
        out.append((base + s, base + e))


def statement_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return (start, end) code-point offsets of every statement in ``text``."""
    out: list[tuple[int, int]] = []
    base = 0
    for line in text.split("\n"):
        i = len(line) - len(line.lstrip())
        marker = _LIST_MARKER.match(line, i)
        start = marker.end() if marker else i
        n = len(line)
        for j in range(start, n):
            ch = line[j]
            if ch in _TERMINATORS and (j + 1 == n or line[j + 1].isspace()):
                _emit(line, base, start, j if ch != "?" else j + 1, out)
                start = j + 1
        _emit(line, base, start, n, out)
        base += n + 1
    return tuple(out)


def statement_at(text: str, start: int, end: int) -> bool:
    """True iff [start, end) is exactly one statement span of ``text``."""
    return (start, end) in statement_spans(text)
