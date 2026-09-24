"""DIFF-001 possible copied-forward text (Tier 3, Section 8.3). A review question, never a
verdict.

Raised when a reassuring or discharge-readiness statement (registry ``status`` terms, live,
not queried) is carried forward verbatim or near-verbatim from an EARLIER source, and a
deterioration marker (an observation beyond a registry ``deterioration_*`` threshold) sits in
a source strictly between the origin and the repeat. Carried text that later evidence does
not contradict raises nothing. Critical-value thresholds are not deterioration markers here
(@kaopilot, 22 Sep: SpO2/RR stay a DIFF-001 question in v1).

Subject: status:<term>@source:<source_id of the repeating note>. Evidence: claim = the
repeat, origin = the first appearance, counter_claim = the marker statements in between.
Owner: the repeating note's author.
"""

from __future__ import annotations

from noteguard.contracts.types import EvidenceRole, FactType, Polarity, RuleId

from ..context import Candidate, Context
from ..extract import Fact, Stmt
from .common import items, more, render

RULE = RuleId.DIFF_001


def evaluate(ctx: Context) -> list[Candidate]:
    rule = ctx.rules[RULE]
    repeats = [f for f in ctx.facts if f.fact_type is FactType.CLINICAL_STATUS and f.polarity is Polarity.PRESENT
               and not f.review_required and f.stmt.carried_from is not None]
    markers = [f for f in ctx.facts if f.fact_type is FactType.OBSERVATION and f.is_deterioration
               and f.polarity is Polarity.PRESENT]
    groups: dict[str, list[tuple[Fact, Stmt, list[Stmt]]]] = {}
    for f in repeats:
        origin = f.stmt.carried_from
        between = list(dict.fromkeys(m.stmt for m in markers if origin.doc.order < m.doc.order < f.doc.order))
        if between:
            groups.setdefault(f"{f.subject_key}@source:{f.doc.source_id}", []).append((f, origin, between))
    out = []
    for subject, rows in groups.items():
        seen: set = set()
        ev = items(ctx, RULE, [f.stmt for f, _, _ in rows], EvidenceRole.CLAIM, subject, seen)
        ev += items(ctx, RULE, [o for _, o, _ in rows], EvidenceRole.ORIGIN, subject, seen)
        ev += items(ctx, RULE, [s for _, _, b in rows for s in b], EvidenceRole.COUNTER_CLAIM, subject, seen)
        f, origin, between = rows[0]
        values = dict(source_label=ctx.source_label(f.doc.source_id), claim_quote=ctx.quoted(f.stmt.quote),
                      origin_source_label=ctx.source_label(origin.doc.source_id),
                      counter_source_label=ctx.source_label(between[0].doc.source_id),
                      counter_quote=ctx.quoted(between[0].quote), source_time_label=ctx.hhmm(f.doc.time))
        reason = render(rule.reason_template, **values) + more(len(ev) - 2)
        question = render(rule.question_template, **values) if rule.question_template else None
        out.append(Candidate(RULE, subject, ev, reason=reason, question=question))
    return out
