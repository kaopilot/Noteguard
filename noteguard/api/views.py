"""Server-side view builders (B2). Closure and glance counts use contracts.states only
(blocks_closure / is_unresolved): the one definition every view shares (L14)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from noteguard.contracts import ids, states
from noteguard.contracts.api_models import ChangeView, GlanceView, SourceView
from noteguard.contracts.types import (
    BubbleStatus,
    CheckRunResult,
    ClosureBlocker,
    ClosureStatus,
    ClosureView,
    Decision,
    Evidence,
    EvidenceRole,
    Flag,
    QuestionBubble,
    Source,
    SourceVersion,
    TextExtraction,
)


def _by_age(f: Flag):
    return (f.created_at, f.flag_id)  # oldest first; golden order is hand-declared (compare as sets)


def _blocker(f: Flag) -> ClosureBlocker:
    return ClosureBlocker(flag_id=f.flag_id, tier=f.tier, state=f.state, owner_staff_id=f.owner_staff_id,
                          opened_at=f.created_at)


def closure_view(encounter_id: str, cutoff: datetime, flags: Iterable[Flag], decisions: Iterable[Decision]) -> ClosureView:
    fl = list(flags)
    t1 = sorted((f for f in fl if states.blocks_closure(f.tier, f.state)), key=_by_age)
    t2 = sorted((f for f in fl if int(f.tier) == 2 and states.is_unresolved(f.tier, f.state)), key=_by_age)
    t3 = sum(1 for f in fl if int(f.tier) == 3 and states.is_unresolved(f.tier, f.state))
    status = ClosureStatus.BLOCKED if t1 else (ClosureStatus.CLEAR_WITH_OPEN_TIER2 if t2 else ClosureStatus.CLEAR)
    return ClosureView(encounter_id=encounter_id, cutoff=cutoff, status=status, tier1_blockers=tuple(map(_blocker, t1)),
                       tier2_open=tuple(map(_blocker, t2)), tier3_open_count=t3, decisions=tuple(decisions))


def glance_view(closure: ClosureView, flags: Iterable[Flag], bubbles: Iterable[QuestionBubble]) -> GlanceView:
    fl = list(flags)
    top = [b for b in bubbles if b.status != BubbleStatus.DOCUMENTED][:3]  # same rule as the summary's TOP_QUESTION
    return GlanceView(encounter_id=closure.encounter_id, cutoff=closure.cutoff, closure_status=closure.status,
                      open_tier1=sum(1 for f in fl if int(f.tier) == 1 and states.is_unresolved(f.tier, f.state)),
                      open_tier2=len(closure.tier2_open), open_tier3=closure.tier3_open_count,
                      tier1_owner_ids=tuple(sorted({b.owner_staff_id for b in closure.tier1_blockers})),
                      top_bubble_ids=tuple(b.bubble_id for b in top), top_bubble_statuses=tuple(b.status for b in top))


def source_views(sources: dict[str, Source], versions: Iterable[SourceVersion],
                 extractions: dict[str, TextExtraction]) -> tuple[SourceView, ...]:
    rows = sorted(versions, key=lambda v: (sources[v.source_id].source_time, v.received_at, v.source_version_id))
    return tuple(source_view(sources[v.source_id], v, extractions[v.source_version_id]) for v in rows)


def source_view(s: Source, v: SourceVersion, e: TextExtraction) -> SourceView:
    return SourceView(source_id=s.source_id, note_version_id=v.source_version_id, version=v.version,
                      supersedes_version_id=v.supersedes_version_id, title=s.title, source_type=s.source_type,
                      discipline=s.discipline, author_staff_id=s.author_staff_id, source_time=s.source_time,
                      version_time=v.version_time, received_at=v.received_at, sha256=v.sha256,
                      extraction_status=e.status, extraction_note=e.note, page_count=len(e.pages))


def change_views(result: CheckRunResult) -> tuple[ChangeView, ...]:
    """Engine Change records -> diff-chip data with version-bound evidence (origin -> claim)."""
    by_id = {a.assertion_id: a for a in result.assertions}

    def ev(assertion_id: str | None, role: EvidenceRole) -> Evidence | None:
        a = by_id.get(assertion_id) if assertion_id else None
        if a is None:
            return None
        return Evidence(note_version_id=a.source_version_id, start=a.span.start, end=a.span.end, page=a.span.page,
                        quote=a.quote, quote_sha256=ids.quote_sha256(a.quote), role_in_flag=role)

    return tuple(ChangeView(kind=c.kind, subject_key=c.subject_key, from_evidence=ev(c.from_assertion_id, EvidenceRole.ORIGIN),
                            to_evidence=ev(c.to_assertion_id, EvidenceRole.CLAIM)) for c in result.changes)
