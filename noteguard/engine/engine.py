"""The check engine: a pure implementation of contracts.engine_api.EngineAPI.

No web, file, network, clock or logging access; time and run identity are passed in, and the
same inputs always give the same outputs (assertion and change ids are content hashes).
"""

from __future__ import annotations

from datetime import datetime

from noteguard.contracts import ids
from noteguard.contracts.types import (
    Assertion,
    CheckRun,
    CheckRunOutcome,
    CheckRunResult,
    Decision,
    EncounterSnapshot,
    QuestionBubble,
    RulesetBundle,
    Span,
    Summary,
)

from . import bubbles as bubble_builder
from . import summary as summary_builder
from .context import Context
from .extract import EXTRACTOR, Fact
from .flags import orchestrate
from .rules import evaluate_all


def _assertion(ctx: Context, f: Fact) -> Assertion:
    st = f.stmt
    return Assertion(
        assertion_id=f.aid, source_version_id=st.doc.svid,
        span=Span(start=st.start, end=st.end, page=ctx.page_of(st.doc, st.start)),
        quote=st.quote, fact_type=f.fact_type, subject_key=f.subject_key, value=f.value, unit=f.unit,
        frequency=f.frequency, response_kinds=f.response_kinds, polarity=f.polarity, certainty=f.certainty,
        scope=f.scope, language="und", extractor=EXTRACTOR, review_required=f.review_required,
        carried_forward_from=f.carried_from.aid if f.carried_from else None, is_critical=f.is_critical,
        adjudicated=f.adjudicated)


class Engine:
    is_stub = False

    def run_checks(self, snapshot: EncounterSnapshot, bundle: RulesetBundle, cutoff: datetime, *, run_id: str,
                   evaluated_at: datetime) -> CheckRunResult:
        ctx = Context(snapshot, bundle, cutoff)
        flags = orchestrate(ctx, evaluate_all(ctx), run_id, evaluated_at)
        gaps = any(not d.readable for d in ctx.docs)
        run = CheckRun(run_id=run_id, encounter_id=snapshot.encounter.encounter_id, source_cutoff=cutoff,
                       ruleset_version=bundle.ruleset.ruleset_version, registry_version=bundle.registry.registry_version,
                       source_set_hash=ids.source_set_hash([d.version.sha256 for d in ctx.docs]),
                       started_at=evaluated_at, completed_at=evaluated_at,
                       outcome=CheckRunOutcome.COMPLETED_WITH_EXTRACTION_GAPS if gaps else CheckRunOutcome.COMPLETED)
        return CheckRunResult(run=run, flags=tuple(flags), assertions=tuple(_assertion(ctx, f) for f in ctx.facts),
                              changes=tuple(ctx.changes))

    def answer_bubbles(self, snapshot: EncounterSnapshot, result: CheckRunResult, bundle: RulesetBundle,
                       cutoff: datetime) -> tuple[QuestionBubble, ...]:
        return bubble_builder.answer(Context(snapshot, bundle, cutoff), result)

    def build_summary(self, snapshot: EncounterSnapshot, result: CheckRunResult, bubbles: tuple[QuestionBubble, ...],
                      decisions: tuple[Decision, ...], bundle: RulesetBundle, cutoff: datetime, *,
                      generated_at: datetime) -> Summary:
        return summary_builder.build(Context(snapshot, bundle, cutoff), result, bubbles, decisions, generated_at)
