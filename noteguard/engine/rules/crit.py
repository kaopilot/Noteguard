"""CRIT-001 critical observation without a documented response (Tier 1, Section 8.2/8.5).

A critical observation is an analyte value at or beyond a registry critical threshold
(placeholders pending clinical governance, OPEN-8). A statement that repeats an earlier
critical value of the same analyte together with a response ("K 6.4 reviewed") refers to
that result; it is not a new observation.

Suppressor (8.5, exactly): a statement with a live (non-negated) response cue in the same
clause as the SAME analyte, from a source whose source_time is LATER than the observation,
whose text is not carried forward from an earlier source. Earlier, carried-forward, negated
and other-analyte responses never suppress. Not raised when every observation has one; the
orchestrator turns a previously seen flag into SUPERSEDED, never resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from noteguard.contracts.types import EvidenceRole, FactType, Polarity, RuleId

from ..context import Candidate, Context
from ..extract import Fact, Stmt
from .common import items, more, render

RULE = RuleId.CRIT_001


@dataclass(eq=False)
class CritState:
    analyte: str
    triggers: list[Fact] = field(default_factory=list)  # critical observations needing a response
    unacknowledged: list[Fact] = field(default_factory=list)
    suppressors: list[Stmt] = field(default_factory=list)


def _live_response(f: Fact, analyte: str) -> bool:
    return f.fact_type is FactType.RESPONSE and f.subject_key == analyte and f.polarity is Polarity.PRESENT


def suppressors_for(ctx: Context, obs: Fact) -> list[Stmt]:
    out: list[Stmt] = []
    for f in ctx.facts:
        if (_live_response(f, obs.subject_key) and f.doc.time > obs.doc.time and f.stmt.carried_from is None
                and f.stmt not in out):
            out.append(f.stmt)
    return out


def critical_states(ctx: Context) -> dict[str, CritState]:
    states: dict[str, CritState] = {}
    for f in ctx.facts:
        if f.fact_type is not FactType.OBSERVATION or not f.is_critical:
            continue
        st = states.setdefault(f.subject_key, CritState(f.subject_key))
        refers_back = any(_live_response(g, f.subject_key) for g in f.stmt.facts) and any(
            t.amount == f.amount and t.doc.time < f.doc.time for t in st.triggers)
        if not refers_back:
            st.triggers.append(f)
    for st in states.values():
        for t in st.triggers:
            sup = suppressors_for(ctx, t)
            if not sup:
                st.unacknowledged.append(t)
            st.suppressors += [s for s in sup if s not in st.suppressors]
    return states


def evaluate(ctx: Context) -> list[Candidate]:
    rule = ctx.rules[RULE]
    out = []
    for analyte, st in critical_states(ctx).items():
        if st.unacknowledged:
            claims = items(ctx, RULE, [t.stmt for t in st.unacknowledged], EvidenceRole.CLAIM, analyte)
            first = st.unacknowledged[0]
            reason = render(rule.reason_template, source_label=ctx.source_label(first.doc.source_id),
                            claim_quote=ctx.quoted(first.stmt.quote), cutoff_label=ctx.hhmm(ctx.cutoff)) + more(len(claims))
            out.append(Candidate(RULE, analyte, claims, raised=True, reason=reason))
        else:
            ev = items(ctx, RULE, [t.stmt for t in st.triggers], EvidenceRole.CLAIM, analyte)
            ev += items(ctx, RULE, st.suppressors, EvidenceRole.SUPPRESSOR, analyte)
            out.append(Candidate(RULE, analyte, ev, raised=False))
    return out
