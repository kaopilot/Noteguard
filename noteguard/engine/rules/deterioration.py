"""DET-001 reassurance recorded after a deterioration marker (Tier 1, stretch; Section 8.2).

Built in B1.2; enabled in rulesets/v1.json by CCR-02 (approved by @k, 22 Sep 2026, defaults).

Raises when a reassuring or discharge-readiness statement (registry ``status`` terms, live,
not queried) sits in a source with a LATER source_time than a deterioration marker (an
observation beyond a registry ``deterioration_*`` threshold, placeholders), and no clinician
review of that marker intervenes. Unlike DIFF-001 the reassurance need not be copied.

Clinician review (CCR-02 question 1, default approved): a statement in a CLINICIAN-authored source,
with a live response cue in the same clause as the SAME analyte as the marker, not carried
forward, placed at or after the marker's source and at or before the reassurance statement.
A nurse's escalation, a later normal observation, or a review naming no analyte does not
count (conservative: the flag stays).

Subject: the status term key (one flag per reassurance kind, L1). Evidence: claim = the
reassurance(s), counter_claim = the unreviewed marker statement(s); when every marker is
reviewed the finding is answered (suppressor = the review statements). Owner: responsible
clinician (else attending).
"""

from __future__ import annotations

from noteguard.contracts.types import Discipline, EvidenceRole, FactType, Polarity, RuleId

from ..context import Candidate, Context
from ..extract import Fact, Stmt
from .common import items, more, render

RULE = RuleId.DET_001


def _pos(f: Fact) -> tuple[int, int]:
    return (f.doc.order, f.stmt.idx)


def clinician_reviews(ctx: Context, marker: Fact, reassurance: Fact) -> list[Stmt]:
    out: list[Stmt] = []
    for g in ctx.facts:
        if (g.fact_type is FactType.RESPONSE and g.subject_key == marker.subject_key and g.polarity is Polarity.PRESENT
                and g.stmt.carried_from is None and g.doc.source.discipline is Discipline.CLINICIAN
                and g.doc.order >= marker.doc.order and _pos(g) <= _pos(reassurance) and g.stmt not in out):
            out.append(g.stmt)
    return out


def evaluate(ctx: Context) -> list[Candidate]:
    rule = ctx.rules[RULE]
    reassurances = [f for f in ctx.facts if f.fact_type is FactType.CLINICAL_STATUS and f.polarity is Polarity.PRESENT
                    and not f.review_required]
    markers = [f for f in ctx.facts if f.fact_type is FactType.OBSERVATION and f.is_deterioration
               and f.polarity is Polarity.PRESENT]
    out = []
    for key in dict.fromkeys(f.subject_key for f in reassurances):
        claims: list[Fact] = []
        open_markers: list[Stmt] = []
        answered: list[Fact] = []
        answered_markers: list[Stmt] = []
        reviews: list[Stmt] = []
        for r in (f for f in reassurances if f.subject_key == key):
            before = [m for m in markers if m.doc.time < r.doc.time]
            unreviewed = [m for m in before if not clinician_reviews(ctx, m, r)]
            if unreviewed:
                claims.append(r)
                open_markers += [m.stmt for m in unreviewed if m.stmt not in open_markers]
            elif before:
                answered.append(r)
                answered_markers += [m.stmt for m in before if m.stmt not in answered_markers]
                reviews += [s for m in before for s in clinician_reviews(ctx, m, r) if s not in reviews]
        if claims:
            seen: set = set()
            ev = items(ctx, RULE, [f.stmt for f in claims], EvidenceRole.CLAIM, key, seen)
            ev += items(ctx, RULE, open_markers, EvidenceRole.COUNTER_CLAIM, key, seen)
            r0, m0 = claims[0], open_markers[0]
            values = dict(source_label=ctx.source_label(r0.doc.source_id), claim_quote=ctx.quoted(r0.stmt.quote),
                          counter_source_label=ctx.source_label(m0.doc.source_id), counter_quote=ctx.quoted(m0.quote),
                          source_time_label=ctx.hhmm(r0.doc.time))
            reason = render(rule.reason_template, **values) + more(len(ev) - 1)
            question = render(rule.question_template, **values) if rule.question_template else None
            out.append(Candidate(RULE, key, ev, reason=reason, question=question))
        elif answered:
            seen = set()
            ev = items(ctx, RULE, [f.stmt for f in answered], EvidenceRole.CLAIM, key, seen)
            ev += items(ctx, RULE, answered_markers, EvidenceRole.COUNTER_CLAIM, key, seen)
            ev += items(ctx, RULE, reviews, EvidenceRole.SUPPRESSOR, key, seen)
            out.append(Candidate(RULE, key, ev, raised=False))
    return out
