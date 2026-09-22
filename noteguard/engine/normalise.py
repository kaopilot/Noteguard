"""Normalisation with an offset map (Section 18.3: assertions and evidence always store
ORIGINAL offsets; matching runs on normalised text).

normalise(s) lower-cases, maps every Unicode dash to "-", curly quotes to straight ones,
collapses whitespace runs to one space and drops thousands separators between digits
("5,000" -> "5000"). ``Norm.to_orig[i]`` is the offset in ``s`` of normalised character i,
so any normalised span maps back exactly.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
_CLAUSE_BREAK = re.compile(r"[,;]")
_TOKEN = re.compile(r"\w+(?:[.+/-]\w+)*%?|\?")


@dataclass(frozen=True)
class Norm:
    text: str
    to_orig: tuple[int, ...]  # len(text) + 1 entries; the last maps the end
    clause_starts: tuple[int, ...]  # normalised offsets where each clause begins

    def orig(self, start: int, end: int) -> tuple[int, int]:
        """Original (start, end) for a normalised span, end exclusive."""
        if end <= start:
            return self.to_orig[start], self.to_orig[start]
        return self.to_orig[start], self.to_orig[end - 1] + 1

    def clause(self, pos: int) -> int:
        """Index of the clause (split on , and ;) containing normalised offset ``pos``."""
        idx = 0
        for i, s in enumerate(self.clause_starts):
            if s <= pos:
                idx = i
        return idx

    def clause_end(self, pos: int) -> int:
        c = self.clause(pos)
        return self.clause_starts[c + 1] - 1 if c + 1 < len(self.clause_starts) else len(self.text)

    def tokens_between(self, a: int, b: int) -> int:
        """Number of word tokens strictly between normalised offsets a and b (a <= b)."""
        return len(_TOKEN.findall(self.text[a:b]))


def _is_thousands_comma(s: str, i: int) -> bool:
    if s[i] != "," or i == 0 or not s[i - 1].isdigit():
        return False
    tail = s[i + 1:i + 5]
    return len(tail) >= 3 and tail[:3].isdigit() and (len(tail) == 3 or not tail[3].isdigit())


def normalise(s: str) -> Norm:
    out: list[str] = []
    to_orig: list[int] = []
    prev_space = True  # also trims leading whitespace
    for i, ch in enumerate(s):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                to_orig.append(i)
            prev_space = True
            continue
        if _is_thousands_comma(s, i):
            continue
        prev_space = False
        if unicodedata.category(ch) == "Pd":
            ch = "-"
        ch = _QUOTES.get(ch, ch)
        for low in ch.lower():
            out.append(low)
            to_orig.append(i)
    while out and out[-1] == " ":
        out.pop()
        to_orig.pop()
    text = "".join(out)
    to_orig.append(to_orig[-1] + 1 if to_orig else 0)
    starts = [0] + [m.end() for m in _CLAUSE_BREAK.finditer(text)]
    return Norm(text=text, to_orig=tuple(to_orig), clause_starts=tuple(starts))


def comparable(norm_text: str) -> str:
    """Text for verbatim comparison: word tokens only (case, whitespace, punctuation and
    number formatting are already normalised)."""
    return " ".join(_TOKEN.findall(norm_text)).replace(" ?", "?")


def tokens(norm_text: str) -> list[str]:
    return _TOKEN.findall(norm_text)
