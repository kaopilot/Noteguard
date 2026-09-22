"""Helpers shared by the rule modules. Reason and question text is rendered only from the
templates in ``rulesets/v1.json`` (rule content) with values taken from cited spans."""

from __future__ import annotations

from collections.abc import Iterable

from noteguard.contracts.types import EvidenceRole, RuleId

from ..context import Context, Item
from ..extract import Stmt


def render(template: str, **values: str) -> str:
    return template.format_map(values)


def items(ctx: Context, rule_id: RuleId, stmts: Iterable[Stmt], role: EvidenceRole, subject_key: str,
          seen: set | None = None) -> list[Item]:
    """One evidence item per distinct statement (a statement can hold several facts)."""
    seen = set() if seen is None else seen
    out = []
    for st in stmts:
        if (st.key, role) in seen:
            continue
        seen.add((st.key, role))
        out.append(ctx.span_item(rule_id, st, role, subject_key))
    return out


def more(count: int) -> str:
    """Suffix when a template quotes one statement of several of the same role."""
    extra = count - 1
    if extra <= 0:
        return ""
    return f" ({extra} further cited statement{'s' if extra > 1 else ''} not quoted here.)"
