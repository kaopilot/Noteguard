"""Deterministic extraction (Section 7 ``Assertion``; 8.1 negation and hedging).

Every fact is anchored to a statement span from ``contracts.spans.statement_spans`` in the
ORIGINAL extracted text. Matching runs on normalised text (normalise.py) and never
paraphrases. Negation/uncertainty is a small NegEx-style scope: a negation or uncertainty
cue from the registry scopes forward over the rest of its clause (split on "," and ";"), up
to ``SCOPE_TOKENS`` word tokens and never across a ":" ("No change: amlodipine 10 mg"); a "?" that does not touch a following word makes its whole
clause uncertain ("allergies: nil?"). Uncertain wording becomes ``review_required`` with a
lowered certainty, never a negative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from noteguard.contracts import ids
from noteguard.contracts.spans import statement_spans
from noteguard.contracts.types import (
    AssertionScope,
    Certainty,
    CueKind,
    EncounterSnapshot,
    ExtractionStatus,
    FactType,
    Polarity,
    ResponseKind,
    RuleId,
    RulesetBundle,
    Source,
    SourceVersion,
    TermKind,
    TextExtraction,
)

from . import units
from .normalise import Norm, comparable, normalise
from .registry import Hit, Lexicon

EXTRACTOR = "noteguard-engine@1"
#: NegEx-style window: word tokens after a cue that it can scope over (within one clause).
SCOPE_TOKENS = 6
#: Allergy keyword and allergen must sit within this many tokens of each other, same clause.
ALLERGY_PROXIMITY = 3

_RESPONSE_CUES = {
    CueKind.RESPONSE_REVIEW: ResponseKind.REVIEW,
    CueKind.RESPONSE_REPEAT: ResponseKind.REPEAT,
    CueKind.RESPONSE_TREATMENT: ResponseKind.TREATMENT,
    CueKind.RESPONSE_ESCALATION: ResponseKind.ESCALATION,
    CueKind.RESPONSE_TRANSFER: ResponseKind.TRANSFER,
}
_SEP = re.compile(r"[\s:=(\-]*")
_FILLER = re.compile(r"(?:to|at|of|dose)\s+")
#: analyte term, then ":"/"="/"of"/"is"/"was", then an optional "?"/"~" (queried value), then the number
_OBS_VALUE = re.compile(r"\s*(?:[:=]\s*|(?:of|is|was)\s+)?([?~]\s*)?(\d+(?:\.\d+)?)(?!\d)")
_UNIT_TOKEN = re.compile(r"\s?([^\s,;()]+)")


# ---------------------------------------------------------------------------------------
# Documents and statements
# ---------------------------------------------------------------------------------------


@dataclass(eq=False)
class Mention:
    key: str
    kind: TermKind
    start: int  # normalised offsets within the statement
    end: int
    clause: int
    negated: bool
    uncertain: bool


@dataclass(eq=False)
class Stmt:
    doc: "Doc"
    idx: int
    start: int  # ORIGINAL offsets into the extraction text
    end: int
    quote: str
    norm: Norm
    mentions: list[Mention]
    cues: dict[CueKind, list[Hit]]
    negated_cues: set[tuple[CueKind, int]]  # (kind, start) of cue hits inside a negation scope
    comparable: str  # for verbatim comparison (differencing)
    uncertain_clauses: frozenset[int] = frozenset()
    denials: tuple[Hit, ...] = ()
    facts: list["Fact"] = field(default_factory=list)
    carried_from: "Stmt | None" = None  # set by differencing

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.doc.version.source_version_id, self.start, self.end)

    def live_cues(self, kind: CueKind) -> list[Hit]:
        return [h for h in self.cues.get(kind, []) if (kind, h.start) not in self.negated_cues]

    def has(self, kind: CueKind) -> bool:
        return bool(self.live_cues(kind))


@dataclass(eq=False)
class Doc:
    source: Source
    version: SourceVersion
    extraction: TextExtraction
    order: int  # position in scope order; -1 for out-of-scope versions resolved for citations
    stmts: list[Stmt] = field(default_factory=list)

    @property
    def source_id(self) -> str:
        return self.source.source_id

    @property
    def svid(self) -> str:
        return self.version.source_version_id

    @property
    def time(self) -> datetime:
        return self.source.source_time

    @property
    def readable(self) -> bool:
        return self.extraction.status in (ExtractionStatus.COMPLETE, ExtractionStatus.NOT_APPLICABLE)


@dataclass(eq=False)
class Fact:
    stmt: Stmt
    fact_type: FactType
    subject_key: str
    polarity: Polarity = Polarity.PRESENT
    certainty: Certainty = Certainty.ASSERTED
    scope: AssertionScope = AssertionScope.SPECIFIC
    value: str | None = None
    unit: str | None = None
    amount: float | None = None
    frequency: str | None = None
    response_kinds: tuple[ResponseKind, ...] = ()
    review_required: bool = False
    is_critical: bool = False
    is_deterioration: bool = False
    change_language: bool = False
    explicit_change: bool = False  # set by differencing (L3)
    carried_from: "Fact | None" = None
    adjudicated: bool = False

    @property
    def doc(self) -> Doc:
        return self.stmt.doc

    @property
    def aid(self) -> str:
        s = self.stmt
        pos = next(i for i, f in enumerate(s.facts) if f is self)
        return "asr_" + ids.sha256_hex(ids.canonical_json(
            [s.doc.svid, s.start, s.end, self.fact_type.value, self.subject_key, pos]))[:24]

    def signature(self) -> tuple:
        """Normalised facts, independent of position and wording (rerun matching, 8.4)."""
        return (self.fact_type.value, self.subject_key, self.polarity.value, self.scope.value, self.value,
                self.unit, self.frequency, tuple(k.value for k in self.response_kinds), int(self.certainty))


# ---------------------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------------------


def in_scope(snapshot: EncounterSnapshot, cutoff: datetime) -> list[tuple[Source, SourceVersion, TextExtraction]]:
    """Section 18.3 / engine_api: a Source is in scope iff source_time <= cutoff; its latest
    version with version_time <= cutoff is used. Ordered by (source_time, received_at, id)."""
    ext = {e.source_version_id: e for e in snapshot.extractions}
    rows = []
    for s in snapshot.sources:
        if s.source_time > cutoff:
            continue
        vs = [v for v in snapshot.versions if v.source_id == s.source_id and v.version_time <= cutoff]
        if not vs:
            continue
        v = max(vs, key=lambda v: v.version)
        if v.source_version_id not in ext:
            raise ValueError("snapshot has no extraction for an in-scope source version")
        rows.append((s, v, ext[v.source_version_id]))
    rows.sort(key=lambda r: (r[0].source_time, r[1].received_at, r[1].source_version_id))
    return rows


# ---------------------------------------------------------------------------------------
# Statement analysis
# ---------------------------------------------------------------------------------------


class Extractor:
    """Builds Docs, Stmts and Facts for one ruleset bundle."""

    def __init__(self, bundle: RulesetBundle, lex: Lexicon) -> None:
        self.lex = lex
        kinds = {r.rule_id: tuple(r.registry_term_kinds) for r in bundle.ruleset.rules}
        self.allergen_kinds = frozenset(kinds.get(RuleId.ALG_001, ()))
        self.drug_kinds = frozenset(kinds.get(RuleId.DOSE_001, ()))
        self.pending_kinds = frozenset(kinds.get(RuleId.PEND_001, ()))
        # status terms feed DIFF-001 and DET-001 (DET also lists analytes, which CRIT-001 already covers)
        self.status_kinds = frozenset(kinds.get(RuleId.DIFF_001, ())) | (frozenset(kinds.get(RuleId.DET_001, ()))
                                                                         & {TermKind.STATUS})
        self.analyte_kinds = frozenset(kinds.get(RuleId.CRIT_001, ()))

    # --- documents ---------------------------------------------------------------------

    def doc(self, source: Source, version: SourceVersion, extraction: TextExtraction, order: int) -> Doc:
        d = Doc(source=source, version=version, extraction=extraction, order=order)
        for i, (a, b) in enumerate(statement_spans(extraction.text)):
            st = self._statement(d, i, a, b)
            d.stmts.append(st)
            st.facts = self._facts(st)
        return d

    def _statement(self, d: Doc, idx: int, a: int, b: int) -> Stmt:
        quote = d.extraction.text[a:b]
        norm = normalise(quote)
        text = norm.text
        cues = {k: self.lex.find_cues(k, text) for k in CueKind}
        denials = self.lex.find_denials(text)
        inside_denial = lambda h: any(dn.start <= h.start and h.end <= dn.end for dn in denials)  # noqa: E731
        neg_hits = [h for h in cues[CueKind.NEGATION] if not inside_denial(h)]
        unc_hits = cues[CueKind.UNCERTAINTY]
        uncertain_clauses = set()
        unc_forward: list[Hit] = []
        for h in unc_hits:
            if text[h.start:h.end] == "?" and not (h.end < len(text) and text[h.end].isalnum()):
                uncertain_clauses.add(norm.clause(h.start))
            else:
                unc_forward.append(h)

        def scoped(pos: int, hits: list[Hit]) -> bool:
            c = norm.clause(pos)
            return any(h.end <= pos and norm.clause(h.start) == c and ":" not in text[h.end:pos]
                       and norm.tokens_between(h.end, pos) <= SCOPE_TOKENS for h in hits)

        mentions = []
        for h in self.lex.find_terms(text):
            kind = self.lex.kind(h.value)
            mentions.append(Mention(key=h.value, kind=kind, start=h.start, end=h.end, clause=norm.clause(h.start),
                                    negated=scoped(h.start, neg_hits),
                                    uncertain=norm.clause(h.start) in uncertain_clauses or scoped(h.start, unc_forward)
                                    or (h.start > 0 and text[h.start - 1] == "?")))
        negated_cues = {(k, h.start) for k in CueKind if k is not CueKind.NEGATION
                        for h in cues[k] if scoped(h.start, neg_hits)}
        cues[CueKind.NEGATION] = neg_hits
        return Stmt(doc=d, idx=idx, start=a, end=b, quote=quote, norm=norm, mentions=mentions, cues=cues,
                    negated_cues=negated_cues, comparable=_comparable(text, mentions),
                    uncertain_clauses=frozenset(uncertain_clauses), denials=tuple(denials))

    # --- facts -------------------------------------------------------------------------

    def _facts(self, st: Stmt) -> list[Fact]:
        out: list[Fact] = []
        out += self._allergy(st)
        consumed: list[tuple[int, int]] = []
        out += self._medication(st, consumed)
        out += self._unparsed(st, consumed)
        out += self._observations(st)
        out += self._pending(st)
        out += self._status(st)
        return out

    def _certainty(self, uncertain: bool) -> Certainty:
        return Certainty.QUERIED if uncertain else Certainty.ASSERTED

    def _allergy(self, st: Stmt) -> list[Fact]:
        out = []
        norm = st.norm
        for dn in st.denials:
            # "?nkda", "nkda?", "query nkda" or a clause ending in "?" -> review, never a denial
            unc = norm.clause(dn.start) in st.uncertain_clauses or any(
                h.end == dn.start or dn.end <= h.start <= dn.end + 1
                or (h.end <= dn.start and norm.clause(h.start) == norm.clause(dn.start))
                for h in st.cues[CueKind.UNCERTAINTY])
            scope = self.lex.denial_scope(dn.value)
            out.append(Fact(stmt=st, fact_type=FactType.ALLERGY, subject_key=f"allergy_denial:{scope.value}",
                            polarity=Polarity.UNKNOWN if unc else Polarity.ABSENT,
                            certainty=Certainty.QUERIED if unc else Certainty.ASSERTED, scope=scope,
                            review_required=unc))
        keywords = st.cues.get(CueKind.ALLERGY_KEYWORD, [])
        named = []
        for m in st.mentions:
            if m.kind not in self.allergen_kinds:
                continue
            near = [k for k in keywords if norm.clause(k.start) == m.clause and norm.tokens_between(
                min(k.end, m.end), max(k.start, m.start)) <= ALLERGY_PROXIMITY]
            if not near:
                continue
            kw_negated = all((CueKind.ALLERGY_KEYWORD, k.start) in st.negated_cues for k in near)
            negated = m.negated or kw_negated
            named.append(Fact(stmt=st, fact_type=FactType.ALLERGY, subject_key=m.key,
                              polarity=Polarity.ABSENT if negated else Polarity.PRESENT,
                              certainty=self._certainty(m.uncertain), review_required=m.uncertain,
                              scope=AssertionScope.CLASS if m.kind is TermKind.DRUG_CLASS else AssertionScope.SPECIFIC))
        out += named
        if keywords and not out and st.cues[CueKind.NEGATION]:
            # A denial that names no substance and is not a registry denial phrase: review, never NKDA (8.1).
            out.append(Fact(stmt=st, fact_type=FactType.ALLERGY, subject_key="allergy_denial:unrecognised",
                            polarity=Polarity.UNKNOWN, certainty=Certainty.UNKNOWN, review_required=True))
        return out

    def _medication(self, st: Stmt, consumed: list[tuple[int, int]]) -> list[Fact]:
        out = []
        text, norm = st.norm.text, st.norm
        drugs = [m for m in st.mentions if m.kind in self.drug_kinds]
        change_hits = st.live_cues(CueKind.CHANGE)
        for i, m in enumerate(drugs):
            nxt = [d.start for d in drugs[i + 1:]] + [j for j in (text.find(";", m.end),) if j >= 0] + [len(text)]
            window_end = min(nxt)
            pos = _SEP.match(text, m.end).end()
            while pos < window_end:
                e = self.lex.cue_at(CueKind.CHANGE, text, pos)
                f = _FILLER.match(text, pos)
                if e is not None:
                    pos = _SEP.match(text, e).end()
                elif f:
                    pos = f.end()
                else:
                    break
            dose = next((d for d in self.lex.find_doses(text) if d[0] == pos and d[1] <= window_end), None)
            fact = Fact(stmt=st, fact_type=FactType.MEDICATION, subject_key=m.key,
                        polarity=Polarity.ABSENT if m.negated else Polarity.PRESENT,
                        certainty=self._certainty(m.uncertain), review_required=m.uncertain,
                        change_language=any(norm.clause(h.start) == m.clause for h in change_hits))
            if dose:
                amount, unit = units.canonical(dose[2], dose[3])
                consumed.append((dose[0], dose[1]))
                freq = next((h for h in self.lex.find_frequencies(text) if dose[1] <= h.start < window_end), None)
                fact.amount, fact.unit = amount, unit
                fact.value = f"{units.fmt(amount)} {unit}"
                fact.frequency = freq.value if freq else None
            out.append(fact)
        return out

    def _unparsed(self, st: Stmt, consumed: list[tuple[int, int]]) -> list[Fact]:
        loose = [d for d in self.lex.find_doses(st.norm.text) if (d[0], d[1]) not in consumed]
        if not loose:
            return []
        subject = f"unparsed_dose@source:{st.doc.source_id}:{ids.sha256_hex(st.quote)[:16]}"
        return [Fact(stmt=st, fact_type=FactType.UNPARSED_DOSE, subject_key=subject, review_required=True,
                     value=", ".join(st.norm.text[a:b] for a, b, _, _ in loose))]

    def _observations(self, st: Stmt) -> list[Fact]:
        out = []
        text, norm = st.norm.text, st.norm
        responses = [(k, h) for k in _RESPONSE_CUES for h in st.cues.get(k, [])]
        live_kinds = tuple(dict.fromkeys(_RESPONSE_CUES[k] for k, h in responses
                                         if (k, h.start) not in st.negated_cues))
        for m in st.mentions:
            if m.kind not in self.analyte_kinds:
                continue
            term = self.lex.term(m.key)
            mv = _OBS_VALUE.match(text, m.end)
            if mv:
                value = float(mv.group(2))
                queried = m.uncertain or mv.group(1) is not None
                unit = None
                mu = _UNIT_TOKEN.match(text, mv.end())
                expected = (term.unit or "").lower()
                if mu:
                    tok = mu.group(1).rstrip(".")
                    if tok == "%" or "/" in tok or (expected and tok == expected):
                        unit = tok
                mismatch = unit is not None and bool(expected) and unit != expected
                crit = not mismatch and ((term.critical_high is not None and value >= term.critical_high)
                                         or (term.critical_low is not None and value <= term.critical_low))
                det = not mismatch and ((term.deterioration_below is not None and value < term.deterioration_below)
                                        or (term.deterioration_at_or_above is not None
                                            and value >= term.deterioration_at_or_above))
                # A queried value stays critical (it still needs a documented response) and is
                # marked review_required; an unparseable value is never read as reassurance.
                out.append(Fact(stmt=st, fact_type=FactType.OBSERVATION, subject_key=m.key,
                                polarity=Polarity.ABSENT if m.negated else Polarity.PRESENT,
                                certainty=self._certainty(queried), value=mv.group(2), unit=unit or term.unit,
                                amount=value, review_required=mismatch or queried,
                                is_critical=crit and not m.negated, is_deterioration=det and not m.negated))
            same_clause = [(k, h) for k, h in responses if norm.clause(h.start) == m.clause]
            if same_clause:
                live = [(k, h) for k, h in same_clause if (k, h.start) not in st.negated_cues]
                out.append(Fact(stmt=st, fact_type=FactType.RESPONSE, subject_key=m.key,
                                polarity=Polarity.PRESENT if live else Polarity.ABSENT,
                                certainty=self._certainty(m.uncertain), review_required=m.uncertain,
                                response_kinds=live_kinds if live else ()))
        return out

    def _pending(self, st: Stmt) -> list[Fact]:
        if not st.has(CueKind.PENDING):
            return []
        return [Fact(stmt=st, fact_type=FactType.PENDING_ACTION, subject_key=m.key,
                     certainty=self._certainty(m.uncertain), review_required=m.uncertain)
                for m in _unique(st.mentions) if m.kind in self.pending_kinds and not m.negated]

    def _status(self, st: Stmt) -> list[Fact]:
        return [Fact(stmt=st, fact_type=FactType.CLINICAL_STATUS, subject_key=m.key,
                     polarity=Polarity.ABSENT if m.negated else Polarity.PRESENT,
                     certainty=self._certainty(m.uncertain), review_required=m.uncertain)
                for m in _unique(st.mentions) if m.kind in self.status_kinds]


def _unique(mentions: list[Mention]) -> list[Mention]:
    seen, out = set(), []
    for m in mentions:
        if m.key not in seen:
            seen.add(m.key)
            out.append(m)
    return out


def _comparable(text: str, mentions: list[Mention]) -> str:
    """Normalised text with registry synonyms replaced by their term key (8.3)."""
    parts, pos = [], 0
    for m in mentions:
        parts.append(text[pos:m.start])
        parts.append(" " + m.key.replace(":", "_") + " ")
        pos = m.end
    parts.append(text[pos:])
    return comparable("".join(parts))
