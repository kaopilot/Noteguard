"""Rule dispatch. Every rule is a pure function Context -> list[Candidate], individually
testable (8.1). A rule enabled in the ruleset but not built here raises NotImplementedError:
the engine never skips an enabled rule silently (L10)."""

from __future__ import annotations

from collections.abc import Callable

from noteguard.contracts.types import RuleId

from ..context import Candidate, Context
from . import completeness, conflicts, copied, crit

BUILT: dict[RuleId, Callable[[Context], list[Candidate]]] = {
    RuleId.CRIT_001: crit.evaluate,
    RuleId.ALG_001: conflicts.allergy,
    RuleId.DOSE_001: conflicts.dose,
    RuleId.DOSE_002: completeness.unparsed_dose,
    RuleId.PEND_001: completeness.pending,
    RuleId.PDF_001: completeness.unreadable,
    RuleId.DIFF_001: copied.evaluate,
    RuleId.OWN_001: completeness.no_responsible_clinician,
}


def evaluate_all(ctx: Context) -> list[Candidate]:
    out: list[Candidate] = []
    for rule in ctx.bundle.ruleset.rules:
        if not rule.enabled:
            continue
        fn = BUILT.get(rule.rule_id)
        if fn is None:
            raise NotImplementedError(f"B1: rule {rule.rule_id.value} is enabled in the ruleset but not built")
        out += fn(ctx)
    return out
