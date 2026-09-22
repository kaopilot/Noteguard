"""Conflict rules. One disagreement = one flag (L1): identity is (rule, encounter, subject),
and every repeated assertion attaches as evidence. Nothing is resolved by source priority;
only a human adjudicates (L2, handled by the orchestrator).

ALG-001 (Tier 1): an all-drug denial (registry denial phrase, e.g. NKDA) or all-allergy
denial, or a specific denial of a related substance, versus a named allergy. Subject = the
named allergen's registry key. ``claim`` = the denial side, ``counter_claim`` = the named
allergy side, whatever their order (README convention 4). A queried allergy ("?penicillin
allergy") still counts as the named side: a possible allergy against a denial needs a
clinician. An unrecognised or queried denial ("allergies: nil?") is review_required and is
never used as a denial (8.1).

DOSE-001 (Tier 2): the same drug with a different dose, unit or frequency across sources.
Regimens are compared after unit canonicalisation and frequency normalisation; a missing
frequency is "not stated", not a different one. An explicit change (L3, see diff.py) starts
a new comparison epoch, so a documented change is never a conflict. Otherwise the first
regimen in an epoch is the claim side and every differing regimen the counter side.
"""

from __future__ import annotations

from noteguard.contracts.types import AssertionScope, EvidenceRole, FactType, Polarity, RuleId

from ..context import Candidate, Context
from ..extract import Fact
from .common import items, more, render

_ALL = frozenset({AssertionScope.ALL_DRUGS, AssertionScope.ALL_ALLERGIES})


def _ordered_keys(facts: list[Fact]) -> list[str]:
    return list(dict.fromkeys(f.subject_key for f in facts))


def allergy(ctx: Context) -> list[Candidate]:
    rule_id = RuleId.ALG_001
    rule = ctx.rules[rule_id]
    facts = [f for f in ctx.facts if f.fact_type is FactType.ALLERGY]
    denials = [f for f in facts if f.scope in _ALL and f.polarity is Polarity.ABSENT and not f.review_required]
    specific = [f for f in facts if f.scope not in _ALL and f.polarity is Polarity.ABSENT]
    named = [f for f in facts if f.scope not in _ALL and f.polarity is Polarity.PRESENT]
    out = []
    for key in _ordered_keys(named):
        counters = [f for f in named if f.subject_key == key]
        claims = [d for d in denials if d.scope is AssertionScope.ALL_ALLERGIES or ctx.lex.is_drug_related(key)]
        claims += [s for s in specific if ctx.lex.related(s.subject_key, key)]
        if not claims:
            continue
        claims.sort(key=lambda f: (f.doc.order, f.stmt.idx))
        ev = items(ctx, rule_id, [f.stmt for f in claims], EvidenceRole.CLAIM, key)
        ev += items(ctx, rule_id, [f.stmt for f in counters], EvidenceRole.COUNTER_CLAIM, key)
        c0, x0 = claims[0], counters[0]
        reason = render(rule.reason_template, claim_source_label=ctx.source_label(c0.doc.source_id),
                        claim_quote=ctx.quoted(c0.stmt.quote), counter_source_label=ctx.source_label(x0.doc.source_id),
                        counter_quote=ctx.quoted(x0.stmt.quote)) + more(len(ev) - 1)
        out.append(Candidate(rule_id, key, ev, reason=reason))
    return out


def _compatible(a: Fact, b: Fact) -> bool:
    return (a.unit == b.unit and a.amount is not None and b.amount is not None and abs(a.amount - b.amount) < 1e-9
            and (a.frequency is None or b.frequency is None or a.frequency == b.frequency))


def dose(ctx: Context) -> list[Candidate]:
    rule_id = RuleId.DOSE_001
    rule = ctx.rules[rule_id]
    meds = [f for f in ctx.facts if f.fact_type is FactType.MEDICATION and f.polarity is Polarity.PRESENT]
    out = []
    for key in _ordered_keys(meds):
        epochs: list[list[Fact]] = [[]]
        for f in (m for m in meds if m.subject_key == key):
            if f.explicit_change:
                epochs.append([])
            epochs[-1].append(f)
        claims: list[Fact] = []
        counters: list[Fact] = []
        for ep in epochs:
            regs = [f for f in ep if f.amount is not None]
            if len(regs) < 2:
                continue
            same = [r for r in regs if _compatible(r, regs[0])]
            other = [r for r in regs if not _compatible(r, regs[0])]
            if other and len({r.doc.source_id for r in same + other}) >= 2:
                claims += same
                counters += other
        if not counters:
            continue
        ev = items(ctx, rule_id, [f.stmt for f in claims], EvidenceRole.CLAIM, key)
        ev += items(ctx, rule_id, [f.stmt for f in counters], EvidenceRole.COUNTER_CLAIM, key)
        c0, x0 = claims[0], counters[0]
        reason = render(rule.reason_template, claim_source_label=ctx.source_label(c0.doc.source_id),
                        claim_quote=ctx.quoted(c0.stmt.quote), counter_source_label=ctx.source_label(x0.doc.source_id),
                        counter_quote=ctx.quoted(x0.stmt.quote)) + more(len(ev) - 1)
        out.append(Candidate(rule_id, key, ev, reason=reason))
    return out
