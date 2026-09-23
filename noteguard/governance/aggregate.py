"""Aggregate risk view (B4; Section 11 "Aggregate risk view", REVIEW_STANDARD_OBSERVATIONS §4.2).

Pure: B2's store supplies content-free, identifier-free rows (``store.aggregate_rows``, which
re-checks the aggregate role at the store layer); this module buckets and counts them into the
frozen ``AggregateView``. No clinical text, no patient, encounter, flag, staff or source ids.

Small cells: any count below the threshold (5) is shown as "<5" (primary suppression). Known gap:
no complementary suppression, so a viewer who knows a row total could difference a small cell out.
Zero cells are not emitted. In the demonstrator every per-user workspace is a copy of the same
synthetic case, so counts are workspace copies, not distinct encounters (declared).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

from noteguard.contracts.api_models import AggregateCell, AggregateView

SMALL_CELL_THRESHOLD = 5
#: Age since the flag was first raised, at generation time. Upper bounds are exclusive.
AGE_BUCKETS: tuple[tuple[timedelta, str], ...] = ((timedelta(hours=4), "<4h"), (timedelta(hours=24), "4-24h"))
AGE_BUCKET_OLDEST = ">24h"


def age_bucket(created_at: datetime, now: datetime) -> str:
    age = now - created_at
    for bound, label in AGE_BUCKETS:
        if age < bound:
            return label
    return AGE_BUCKET_OLDEST


def build_view(rows: Iterable, *, now: datetime, ruleset_version: str,
               threshold: int = SMALL_CELL_THRESHOLD) -> AggregateView:
    """``rows``: objects with rule_id, tier, state, created_at (B2's AggregateRow). Only these four
    fields are read; nothing else from a row can reach the view."""
    counts = Counter((r.rule_id, r.tier, r.state, age_bucket(r.created_at, now)) for r in rows)
    cells = tuple(
        AggregateCell(rule_id=rule_id, tier=tier, state=state, age_bucket=bucket,
                      count=str(n) if n >= threshold else f"<{threshold}")
        for (rule_id, tier, state, bucket), n in sorted(counts.items(), key=lambda kv: (
            kv[0][0].value, int(kv[0][1]), kv[0][2].value, kv[0][3])))
    return AggregateView(generated_at=now, ruleset_version=ruleset_version, cells=cells,
                         small_cell_threshold=threshold)
