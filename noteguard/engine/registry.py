"""Term registry index (L5). Every term, synonym, denial, frequency, dose unit and cue the
engine uses comes from ``bundle.registry``; this module only compiles matchers over it.
It holds no vocabulary of its own (test_single_term_registry, the B0 seam test).

Matching runs on normalised text (normalise.py): lower case, unified dashes, collapsed
whitespace. Literal phrases match on word boundaries; the TIMING and OWNER cue lists are
regular expressions by contract (types.CueKind).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from noteguard.contracts.types import AssertionScope, CueKind, Term, TermKind, TermRegistry

#: Cue kinds whose registry entries are regular expressions, not literal phrases.
_REGEX_CUES = frozenset({CueKind.TIMING, CueKind.OWNER})


def _literal(phrase: str) -> str:
    """Regex for a literal phrase with word boundaries on its word-character edges."""
    body = re.escape(phrase)
    left = r"(?<!\w)" if phrase[:1].isalnum() else ""
    right = r"(?!\w)" if phrase[-1:].isalnum() else ""
    return left + body + right


def _alternation(patterns: list[str]) -> re.Pattern[str] | None:
    return re.compile("|".join(f"(?:{p})" for p in patterns)) if patterns else None


@dataclass(frozen=True)
class Hit:
    start: int  # offsets into the normalised text of one statement
    end: int
    value: str  # term key, cue kind value, denial scope or frequency, depending on matcher


class Lexicon:
    """Compiled, read-only view of one TermRegistry version."""

    def __init__(self, registry: TermRegistry) -> None:
        self.version = registry.registry_version
        self.terms: dict[str, Term] = {t.key: t for t in registry.terms}
        phrases: dict[str, str] = {}
        for t in registry.terms:
            for s in t.synonyms:
                p = s.lower()
                if phrases.get(p, t.key) != t.key:
                    raise ValueError(f"registry {self.version}: synonym shared by two terms")
                phrases[p] = t.key
        self._term_of = phrases
        # Longest phrase first, so the leftmost match at a position is the longest one.
        ordered = sorted(phrases, key=lambda p: (-len(p), p))
        self._term_re = _alternation([_literal(p) for p in ordered])
        denials = sorted(registry.allergy_denials, key=lambda d: -len(d.phrase))
        self._denial_scope = {d.phrase.lower(): d.scope for d in denials}
        self._denial_re = _alternation([_literal(d.phrase.lower()) for d in denials])
        freqs = sorted(registry.frequencies, key=lambda f: -len(f.phrase))
        self._freq_of = {f.phrase.lower(): f.normalised for f in freqs}
        self._freq_re = _alternation([_literal(f.phrase.lower()) for f in freqs])
        units = sorted({u.lower() for u in registry.dose_units}, key=lambda u: (-len(u), u))
        self.dose_units = tuple(units)
        # number (thousands commas already removed by normalise) + optional space + dose unit;
        # a following "/" means a concentration (g/L), which is not a dose.
        self._dose_re = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(" + "|".join(re.escape(u) for u in units)
                                   + r")(?![\w/])") if units else None
        self._cue_re: dict[CueKind, re.Pattern[str] | None] = {}
        for kind in CueKind:
            entries = [c.lower() for c in registry.cues.get(kind, ())]
            if kind in _REGEX_CUES:
                pats = [rf"(?<!\w){c}(?!\w)" for c in entries]
            else:
                pats = [_literal(c) for c in sorted(entries, key=lambda c: -len(c))]
            self._cue_re[kind] = _alternation(pats)

    # --- terms -------------------------------------------------------------------------

    def term(self, key: str) -> Term:
        return self.terms[key]

    def kind(self, key: str) -> TermKind | None:
        t = self.terms.get(key)
        return t.kind if t else None

    def label(self, key: str) -> str:
        """Display label of a term: its first synonym (fixtures/expected/README.md, 8)."""
        t = self.terms.get(key)
        return t.synonyms[0] if t else key

    def find_terms(self, text: str) -> list[Hit]:
        if self._term_re is None:
            return []
        return [Hit(m.start(), m.end(), self._term_of[m.group(0)]) for m in self._term_re.finditer(text)]

    def related(self, a: str, b: str) -> bool:
        """Same term, or one names the other as a class (allergen:penicillin <-> drug_class:penicillins)."""
        if a == b:
            return True
        ta, tb = self.terms.get(a), self.terms.get(b)
        return bool((ta and b in ta.classes) or (tb and a in tb.classes)
                    or (ta and tb and set(ta.classes) & set(tb.classes)))

    def is_drug_related(self, key: str) -> bool:
        """True for drugs, drug classes and allergens that belong to a drug class."""
        t = self.terms.get(key)
        if t is None:
            return False
        if t.kind in (TermKind.DRUG, TermKind.DRUG_CLASS):
            return True
        return any(self.kind(c) is TermKind.DRUG_CLASS for c in t.classes)

    # --- phrases and cues --------------------------------------------------------------

    def find_denials(self, text: str) -> list[Hit]:
        if self._denial_re is None:
            return []
        return [Hit(m.start(), m.end(), self._denial_scope[m.group(0)].value) for m in self._denial_re.finditer(text)]

    def denial_scope(self, value: str) -> AssertionScope:
        return AssertionScope(value)

    def find_frequencies(self, text: str) -> list[Hit]:
        if self._freq_re is None:
            return []
        return [Hit(m.start(), m.end(), self._freq_of[m.group(0)]) for m in self._freq_re.finditer(text)]

    def find_doses(self, text: str) -> list[tuple[int, int, float, str]]:
        """(start, end, amount, unit) for every number + dose unit (L4 broad catch)."""
        if self._dose_re is None:
            return []
        return [(m.start(), m.end(), float(m.group(1)), m.group(2)) for m in self._dose_re.finditer(text)]

    def find_cues(self, kind: CueKind, text: str) -> list[Hit]:
        rx = self._cue_re.get(kind)
        if rx is None:
            return []
        return [Hit(m.start(), m.end(), kind.value) for m in rx.finditer(text)]

    def cue_at(self, kind: CueKind, text: str, pos: int) -> int | None:
        """End offset of a cue of ``kind`` starting exactly at ``pos``, else None."""
        rx = self._cue_re.get(kind)
        if rx is None:
            return None
        m = rx.match(text, pos)
        return m.end() if m else None
