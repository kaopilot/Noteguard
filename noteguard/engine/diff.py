"""Differencing, "git diff for a patient" (Section 8.3). Produces review material, never a
conclusion.

Carried forward: a statement whose normalised text (case, whitespace, punctuation, number
format, registry synonyms -> term keys) equals, or near-verbatim matches, a statement in an
EARLIER, DIFFERENT source. Near-verbatim = difflib token ratio >= NEAR_VERBATIM with the same
numbers, the same registry terms and the same negated terms, so a changed value or a
dropped "not" is never "the same text". Carried text can never suppress a flag (8.5).

Each fact with a subject is then classified against the most recent earlier fact on the same
subject: carried_forward (its statement was carried), explicit_change (L3: change language,
later clinician or pharmacy source, strictly later source time), reworded (same normalised
facts, different words) or new. Nothing is resolved by source priority.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from noteguard.contracts import ids
from noteguard.contracts.types import Change, ChangeKind, Discipline, FactType

from .extract import Doc, Fact, Stmt

NEAR_VERBATIM = 0.9
#: Source disciplines whose explicit change language counts as a change, not a conflict (L3).
CHANGE_AUTHORS = frozenset({Discipline.CLINICIAN, Discipline.PHARMACY})
#: Fact types that take part in differencing (an unparsed dose is keyed per statement).
_DIFFED = frozenset(FactType) - {FactType.UNPARSED_DOSE}


def _numbers(st: Stmt) -> list[str]:
    return [t for t in st.comparable.split() if any(c.isdigit() for c in t) and "_" not in t]


def _near(a: Stmt, b: Stmt) -> bool:
    ta, tb = a.comparable.split(), b.comparable.split()
    if min(len(ta), len(tb)) < 4:
        return False
    if _numbers(a) != _numbers(b):
        return False
    if sorted(m.key for m in a.mentions) != sorted(m.key for m in b.mentions):
        return False
    if sorted(m.key for m in a.mentions if m.negated) != sorted(m.key for m in b.mentions if m.negated):
        return False
    return SequenceMatcher(a=ta, b=tb, autojunk=False).ratio() >= NEAR_VERBATIM


def mark_carried(docs: list[Doc]) -> None:
    seen: list[Stmt] = []
    for d in docs:
        for st in d.stmts:
            st.carried_from = None
            if st.comparable:
                earlier = [o for o in seen if o.doc.source_id != d.source_id]
                exact = [o for o in earlier if o.comparable == st.comparable]
                origin = exact[0] if exact else next((o for o in earlier if _near(o, st)), None)
                if origin is not None:
                    st.carried_from = origin.carried_from or origin
        seen.extend(d.stmts)


def is_explicit_change(f: Fact, prev: Fact | None) -> bool:
    """L3: explicit change language, in a later clinician/pharmacy source, unambiguous order."""
    return (prev is not None and f.fact_type is FactType.MEDICATION and f.change_language
            and f.doc.source.discipline in CHANGE_AUTHORS and f.doc.time > prev.doc.time)


def _change_id(kind: ChangeKind, subject: str, a: Fact | None, b: Fact | None) -> str:
    return "chg_" + ids.sha256_hex(ids.canonical_json([kind.value, subject, a.aid if a else "", b.aid if b else ""]))[:24]


def difference(docs: list[Doc]) -> list[Change]:
    mark_carried(docs)
    history: dict[tuple[FactType, str], list[Fact]] = {}
    out: list[Change] = []
    for d in docs:
        for st in d.stmts:
            for f in st.facts:
                if f.fact_type not in _DIFFED:
                    continue
                key = (f.fact_type, f.subject_key)
                past = history.setdefault(key, [])
                prev = past[-1] if past else None
                origin = None
                if st.carried_from is not None:
                    origin = next((o for o in st.carried_from.facts if (o.fact_type, o.subject_key) == key), None)
                f.explicit_change = False
                if origin is not None:
                    f.carried_from = origin
                    kind, frm = ChangeKind.CARRIED_FORWARD, origin
                elif is_explicit_change(f, prev):
                    f.explicit_change = True
                    kind, frm = ChangeKind.EXPLICIT_CHANGE, prev
                else:
                    same = next((p for p in reversed(past) if p.signature() == f.signature()), None)
                    kind, frm = (ChangeKind.REWORDED, same) if same is not None else (ChangeKind.NEW, None)
                out.append(Change(change_id=_change_id(kind, f.subject_key, frm, f), kind=kind,
                                  subject_key=f.subject_key, from_assertion_id=frm.aid if frm else None,
                                  to_assertion_id=f.aid))
                past.append(f)
    return out
