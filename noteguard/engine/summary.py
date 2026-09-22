"""One-page summary (Section 8.9). Every claim is a deterministic template over flag,
decision or bubble records, with their evidence; no free paraphrase. Claims: one
open_priority per unresolved Tier 1/2 flag (states.is_unresolved), one decision_record per
decision, one top_question for each of the first three bubbles that are not 'documented'.

``stale_after_source_change`` is False at generation: staleness is a comparison with sources
that arrive AFTER generation, which only the caller (API) can observe.
"""

from __future__ import annotations

from datetime import datetime

from noteguard.contracts import states
from noteguard.contracts.types import (
    BubbleStatus,
    CheckRunResult,
    ClosureStatus,
    Decision,
    QuestionBubble,
    Summary,
    SummaryClaim,
    SummaryClaimTemplate,
    TimelineEntry,
)

from .context import Context

TOP_QUESTIONS = 3


def closure_status(result: CheckRunResult) -> ClosureStatus:
    if any(states.blocks_closure(f.tier, f.state) for f in result.flags):
        return ClosureStatus.BLOCKED
    if any(int(f.tier) == 2 and states.is_unresolved(f.tier, f.state) for f in result.flags):
        return ClosureStatus.CLEAR_WITH_OPEN_TIER2
    return ClosureStatus.CLEAR


def build(ctx: Context, result: CheckRunResult, bubbles: tuple[QuestionBubble, ...], decisions: tuple[Decision, ...],
          generated_at: datetime) -> Summary:
    flags = {f.flag_id: f for f in result.flags}
    claims: list[SummaryClaim] = []
    open_flags = sorted((f for f in result.flags if int(f.tier) in (1, 2) and states.is_unresolved(f.tier, f.state)),
                        key=lambda f: (int(f.tier), f.created_at, f.rule_id.value, f.subject_key))
    for f in open_flags:
        claims.append(SummaryClaim(
            template=SummaryClaimTemplate.OPEN_PRIORITY,
            params=dict(flag_id=f.flag_id, rule_id=f.rule_id.value, tier=int(f.tier), state=f.state.value,
                        owner_staff_id=f.owner_staff_id),
            text=f"Tier {int(f.tier)} \u00b7 {f.title} \u00b7 owner {ctx.staff_name(f.owner_staff_id)} \u00b7 {f.state.value}",
            evidence=f.evidence))
    for d in sorted(decisions, key=lambda d: d.at):
        f = flags.get(d.flag_id)
        if f is None:
            raise ValueError("a decision references a flag that is not in this check run")
        params = dict(decision_id=d.decision_id, flag_id=d.flag_id, action=d.action.value,
                      actor_staff_id=d.actor_staff_id, to_state=d.to_state.value, at=d.at.isoformat())
        if d.reason_code is not None:
            params.update(reason_code=d.reason_code.value)
        reason = d.reason_code.value.replace("_", " ") if d.reason_code else "no reason code"
        claims.append(SummaryClaim(
            template=SummaryClaimTemplate.DECISION_RECORD, params=params,
            text=(f"{d.action.value.replace('_', ' ').capitalize()} \u00b7 {f.title} \u00b7 by "
                  f"{ctx.staff_name(d.actor_staff_id)} \u00b7 {reason} \u00b7 {ctx.hhmm(d.at)}"),
            evidence=f.evidence))
    top = [b for b in bubbles if b.status is not BubbleStatus.DOCUMENTED][:TOP_QUESTIONS]
    for b in top:
        claims.append(SummaryClaim(
            template=SummaryClaimTemplate.TOP_QUESTION,
            params=dict(bubble_id=b.bubble_id, question_template_id=b.question_template_id, status=b.status.value),
            text=f"{b.question} \u2014 {b.status.value.replace('_', ' ')}", evidence=b.evidence))
    timeline = tuple(TimelineEntry(source_id=d.source_id, note_version_id=d.svid, version=d.version.version,
                                   author_staff_id=d.source.author_staff_id, discipline=d.source.discipline,
                                   source_type=d.source.source_type, source_time=d.source.source_time,
                                   extraction_status=d.extraction.status, title=d.source.title) for d in ctx.docs)
    e = ctx.encounter
    return Summary(encounter_id=e.encounter_id, encounter_ref=e.encounter_ref, patient_ref=ctx.snapshot.patient.patient_ref,
                   generated_at=generated_at, cutoff=ctx.cutoff, ruleset_version=ctx.bundle.ruleset.ruleset_version,
                   registry_version=ctx.lex.version, closure_status=closure_status(result), timeline=timeline,
                   claims=tuple(claims))
