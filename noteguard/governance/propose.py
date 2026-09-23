"""Offline rule proposals from exported feedback (B4; Section 11 steps 2-3, L13).

Nothing here runs in the request path, and nothing here edits a ruleset: the output is a list of
``RuleProposal`` records that can only reach production as a NEW ruleset version, evaluated
(``evaluate.py``) and approved (``APPROVAL_<v>.md``).

Protected floor (the hint's "critical classes need a floor"): a rule is protected if the BASELINE
ruleset marks it ``protected_floor`` or it is Tier 1. Proposals that lower its tier, disable it,
narrow it, retire it or adjust its threshold are REFUSED. Protection is read from the baseline, so
no proposal can unprotect a rule. A noisy protected rule is fixed by precision work, never by
suppression (L14): its narrowing candidate is emitted as a refusal so governance sees it.

Usage (exported feedback = JSON list of FeedbackEvent):
    uv run python -m noteguard.governance.propose --feedback events.json --target v2 [--out proposals.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from noteguard.contracts import ids
from noteguard.contracts.types import (
    CueKind,
    DecisionAction,
    FeedbackEvent,
    ProposalKind,
    RuleDefinition,
    RuleId,
    RuleProposal,
    Ruleset,
    Tier,
    TermRegistry,
    Usefulness,
)

K = ProposalKind

# Refusal codes (machine codes only).
PROTECTED_FLOOR = "protected_floor"
NARROWS_SHARED_REGISTRY = "narrows_shared_registry"  # a suppressing cue is shared with protected rules
RULE_ID_REQUIRED = "rule_id_required"
UNKNOWN_RULE = "unknown_rule"
UNKNOWN_TERM = "unknown_term"
NOT_TIER3 = "not_tier3"
SAME_VERSION = "must_target_a_new_version"
INVALID_PAYLOAD = "invalid_payload"

#: Kinds that remove or demote flags. On a protected rule these are always refused.
_REDUCING = frozenset({K.LOWER_TIER, K.DISABLE_RULE, K.NARROW_RULE, K.RETIRE_TIER3_RULE, K.ADJUST_TIER3_THRESHOLD})
_NEEDS_RULE = _REDUCING
#: Cue kinds whose added phrases can only ADD detections. Every other cue kind (negation,
#: uncertainty, change, response_*, owner, timing) can remove a flag, and the registry is shared
#: with protected rules, so a synonym for it is refused here and must go through a hand-authored
#: version with a full evaluation.
_WIDENING_CUES = frozenset({CueKind.PENDING, CueKind.ALLERGY_KEYWORD})

# Defaults for the offline noise heuristic (documented in docs/decisions/B4.md).
MIN_SURFACED = 10
NOISY_DISMISSAL_RATE = 0.5
#: REVIEW_STANDARD_OBSERVATIONS §4.2: ~25 words at 2-3 words/s -> under ~2 s means unread.
READING_FLOOR_MS = 2000


def is_protected(rule: RuleDefinition) -> bool:
    return rule.protected_floor or rule.default_tier is Tier.T1


def refusal_code(p: RuleProposal, baseline: Ruleset, registry: TermRegistry | None = None) -> str | None:
    """None = may proceed to offline evaluation. A code = refused (never emitted as a proposal)."""
    if p.target_ruleset_version == baseline.ruleset_version:
        return SAME_VERSION
    rules = {r.rule_id: r for r in baseline.rules}
    if p.kind in _NEEDS_RULE:
        if p.rule_id is None:
            return RULE_ID_REQUIRED
        if p.rule_id not in rules:
            return UNKNOWN_RULE
        rule = rules[p.rule_id]
        if is_protected(rule):
            return PROTECTED_FLOOR
        if p.kind in (K.RETIRE_TIER3_RULE, K.ADJUST_TIER3_THRESHOLD) and rule.default_tier is not Tier.T3:
            return NOT_TIER3
    if p.kind is K.ADD_SYNONYM:
        if "cue_kind" in p.payload:
            try:
                cue = CueKind(p.payload["cue_kind"])
            except ValueError:
                return INVALID_PAYLOAD
            if not isinstance(p.payload.get("phrase"), str) or not p.payload["phrase"].strip():
                return INVALID_PAYLOAD
            if cue not in _WIDENING_CUES:
                return NARROWS_SHARED_REGISTRY
        elif "term_key" in p.payload:
            if not isinstance(p.payload.get("synonym"), str) or not p.payload["synonym"].strip():
                return INVALID_PAYLOAD
            if registry is not None and p.payload["term_key"] not in {t.key for t in registry.terms}:
                return UNKNOWN_TERM
        else:
            return INVALID_PAYLOAD
    return None


# ---------------------------------------------------------------------------------------------
# Metrics (Section 11 step 2). Every rate carries its numerator and denominator.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleMetrics:
    rule_id: RuleId
    surfaced: int
    surfaced_basis: str  # "supplied" (count of surfaced flags) or "flags_with_feedback" (exposure-biased)
    decided: int
    accepted_or_resolved: int
    dismissed: int
    dismissal_reasons: dict[str, int]
    disposition_mix: dict[str, int]
    usefulness: dict[str, int]
    timed_events: int
    fast_events: int  # time_on_screen_ms below the reading floor
    owner_response_time: str = "not_available: FeedbackEvent carries no flag created_at (see aggregate view)"
    rates: dict[str, str] = field(default_factory=dict)


def _rate(n: int, d: int) -> str:
    return f"{n}/{d}" if d else f"{n}/0 (no denominator)"


def rule_metrics(events: Iterable[FeedbackEvent], surfaced: Mapping[RuleId, int] | None = None,
                 reading_floor_ms: int = READING_FLOOR_MS) -> tuple[RuleMetrics, ...]:
    """Per-rule metrics. Events per flag: B2 records one event per decision (usefulness None) and one
    per usefulness post (copying the latest decision's action), so dispositions are counted once per
    FLAG from its latest decision event, never per event."""
    by_rule: dict[RuleId, dict[str, list[FeedbackEvent]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        by_rule[e.rule_id][e.flag_id].append(e)
    out = []
    for rule_id in sorted(set(by_rule) | set(surfaced or {}), key=lambda r: r.value):
        flags = by_rule.get(rule_id, {})
        final: dict[str, FeedbackEvent] = {}
        usefulness: dict[str, int] = defaultdict(int)
        timed = fast = 0
        for fid, evs in flags.items():
            evs = sorted(evs, key=lambda e: e.at)
            decisions = [e for e in evs if e.usefulness is None] or evs
            final[fid] = decisions[-1]
            for e in evs:
                if e.usefulness is not None:
                    usefulness[e.usefulness.value] += 1
                if e.time_on_screen_ms is not None:
                    timed += 1
                    fast += e.time_on_screen_ms < reading_floor_ms
        mix: dict[str, int] = defaultdict(int)
        reasons: dict[str, int] = defaultdict(int)
        for e in final.values():
            mix[e.action.value] += 1
            if e.action is DecisionAction.DISMISS:
                reasons[e.reason_code.value if e.reason_code else "none"] += 1
        acc = mix.get(DecisionAction.ACCEPT.value, 0) + mix.get(DecisionAction.RESOLVE.value, 0)
        dis = mix.get(DecisionAction.DISMISS.value, 0)
        basis = "supplied" if surfaced is not None and rule_id in surfaced else "flags_with_feedback"
        n = surfaced[rule_id] if basis == "supplied" else len(final)
        out.append(RuleMetrics(
            rule_id=rule_id, surfaced=n, surfaced_basis=basis, decided=len(final), accepted_or_resolved=acc,
            dismissed=dis, dismissal_reasons=dict(reasons), disposition_mix=dict(mix), usefulness=dict(usefulness),
            timed_events=timed, fast_events=fast,
            rates={"actionability": _rate(acc, n), "dismissal": _rate(dis, n),
                   "missing_rule_reports": _rate(usefulness.get(Usefulness.MISSING_RULE.value, 0), n),
                   "wrong_owner_reports": _rate(usefulness.get(Usefulness.WRONG_OWNER.value, 0), n),
                   "fast_decision_share": _rate(fast, timed)}))
    return tuple(out)


# ---------------------------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Refusal:
    proposal: RuleProposal
    code: str


@dataclass(frozen=True)
class ProposalBatch:
    accepted: tuple[RuleProposal, ...]  # may proceed to offline evaluation; none is live
    refused: tuple[Refusal, ...]
    metrics: tuple[RuleMetrics, ...]


def make_proposal(kind: ProposalKind, rule_id: RuleId | None, target: str, payload: dict, rationale_code: str,
                  evidence_counts: dict[str, int]) -> RuleProposal:
    pid = "prp_" + ids.sha256_hex(ids.canonical_json([kind.value, rule_id.value if rule_id else None, target,
                                                      payload]))[:24]
    return RuleProposal(proposal_id=pid, kind=kind, rule_id=rule_id, target_ruleset_version=target,
                        payload=payload, rationale_code=rationale_code, evidence_counts=evidence_counts)


def submit(proposals: Iterable[RuleProposal], baseline: Ruleset, registry: TermRegistry | None = None) -> tuple[
        tuple[RuleProposal, ...], tuple[Refusal, ...]]:
    """Every proposal, human-authored or feedback-derived, passes through here."""
    ok, refused = [], []
    for p in proposals:
        code = refusal_code(p, baseline, registry)
        (ok.append(p) if code is None else refused.append(Refusal(p, code)))
    return tuple(ok), tuple(refused)


def propose_from_feedback(events: Iterable[FeedbackEvent], baseline: Ruleset, target_version: str, *,
                          surfaced: Mapping[RuleId, int] | None = None, min_surfaced: int = MIN_SURFACED,
                          noisy_dismissal_rate: float = NOISY_DISMISSAL_RATE,
                          reading_floor_ms: int = READING_FLOOR_MS,
                          registry: TermRegistry | None = None) -> ProposalBatch:
    """A rule is noisy when surfaced >= min_surfaced and dismissed/surfaced >= noisy_dismissal_rate.
    Noisy Tier 3 -> RETIRE_TIER3_RULE candidate; any other noisy rule -> NARROW_RULE candidate. Both
    go through ``submit``: on a protected rule they are refused, which is how governance sees it."""
    metrics = rule_metrics(events, surfaced, reading_floor_ms)
    rules = {r.rule_id: r for r in baseline.rules}
    candidates = []
    for m in metrics:
        rule = rules.get(m.rule_id)
        if rule is None or m.surfaced < min_surfaced or m.dismissed < noisy_dismissal_rate * m.surfaced:
            continue
        kind = K.RETIRE_TIER3_RULE if rule.default_tier is Tier.T3 else K.NARROW_RULE
        candidates.append(make_proposal(kind, m.rule_id, target_version, {}, "noisy_dismissal_rate",
                                        {"dismissed": m.dismissed, "surfaced": m.surfaced}))
    ok, refused = submit(candidates, baseline, registry)
    return ProposalBatch(accepted=ok, refused=refused, metrics=metrics)


def _jsonable(batch: ProposalBatch) -> dict:
    from dataclasses import asdict

    return {"accepted": [p.model_dump(mode="json") for p in batch.accepted],
            "refused": [{"proposal": r.proposal.model_dump(mode="json"), "code": r.code} for r in batch.refused],
            "metrics": [asdict(m) | {"rule_id": m.rule_id.value} for m in batch.metrics]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--feedback", type=Path, required=True, help="JSON list of FeedbackEvent")
    ap.add_argument("--surfaced", type=Path, help="JSON {rule_id: surfaced flag count}")
    ap.add_argument("--ruleset", type=Path, default=Path(__file__).resolve().parents[2] / "rulesets" / "v1.json")
    ap.add_argument("--target", required=True, help="new ruleset version the proposals target, e.g. v2")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    baseline = Ruleset.model_validate_json(a.ruleset.read_bytes())
    events = [FeedbackEvent.model_validate(e) for e in json.loads(a.feedback.read_text(encoding="utf-8"))]
    surfaced = ({RuleId(k): int(v) for k, v in json.loads(a.surfaced.read_text(encoding="utf-8")).items()}
                if a.surfaced else None)
    out = json.dumps(_jsonable(propose_from_feedback(events, baseline, a.target, surfaced=surfaced)), indent=2)
    if a.out:
        a.out.write_text(out + "\n", encoding="utf-8")
    else:
        sys.stdout.write(out + "\n")  # ids, codes and counts only; FeedbackEvent carries no content
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
