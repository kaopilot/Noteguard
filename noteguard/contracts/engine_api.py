"""Engine interface (frozen, B0). B1 implements it in noteguard/engine; the stub in
noteguard/engine_stub.py returns golden fixtures until I1.

The engine is PURE: no web, file, network, clock or logging access. Time and run
identity are passed in. Everything that decides whether a flag exists, its tier,
owner and whether it blocks closure is computed here, deterministically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .types import (
    CheckRunResult,
    Decision,
    EncounterSnapshot,
    QuestionBubble,
    RulesetBundle,
    Summary,
)


@runtime_checkable
class EngineAPI(Protocol):
    def run_checks(
        self,
        snapshot: EncounterSnapshot,
        bundle: RulesetBundle,
        cutoff: datetime,
        *,
        run_id: str,
        evaluated_at: datetime,
    ) -> CheckRunResult:
        """Evaluate every enabled rule over the sources in scope at ``cutoff``.

        Scope: a Source is in scope iff source_time <= cutoff; for each in-scope
        Source the latest SourceVersion with version_time <= cutoff is used.
        Assertions are ordered by (source_time, received_at, source_version_id).
        ``snapshot.prior_flags`` carries flag state from earlier runs: a flag seen
        before and now suppressed becomes SUPERSEDED (never resolved/dismissed);
        a flag never seen and suppressed at evaluation time is simply not raised.
        Returns every flag known for the encounter in its current state.
        """
        ...

    def answer_bubbles(
        self,
        snapshot: EncounterSnapshot,
        result: CheckRunResult,
        bundle: RulesetBundle,
        cutoff: datetime,
    ) -> tuple[QuestionBubble, ...]:
        """Deterministic bubbles from the question catalog. Each answer is one of the
        five BubbleStatus values. not_documented_in_supplied_sources only when EVERY
        in-scope source has extraction status complete or not_applicable; otherwise
        incomplete_extraction naming the unread sources. Ordered by (rank, subject_key)."""
        ...

    def build_summary(
        self,
        snapshot: EncounterSnapshot,
        result: CheckRunResult,
        bubbles: tuple[QuestionBubble, ...],
        decisions: tuple[Decision, ...],
        bundle: RulesetBundle,
        cutoff: datetime,
        *,
        generated_at: datetime,
    ) -> Summary:
        """One-page summary. Every claim is a template over flag/decision/bubble
        records with evidence; no free paraphrase. Claims: one OPEN_PRIORITY per
        unresolved Tier 1/2 flag (states.is_unresolved); one DECISION_RECORD per
        decision; one TOP_QUESTION for each of the first three bubbles whose status
        is not 'documented'."""
        ...
