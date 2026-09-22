"""Flag orchestration (Sections 8.4-8.6, L1, L2).

Identity: ``contracts.ids.flag_id(rule_id, encounter_id, subject_key)``; rule version and
evidence are not part of it, so reruns never duplicate a flag.

Rerun merge (README convention 7). Evidence items are matched on (source, role, normalised
facts of the cited statement), so an amendment that restates the same facts keeps the
original citation and sets ``source_changed_since_flag`` (revision +1, evidence_revision
unchanged). New items carry the new evidence_revision; cited items are never dropped (they
stay resolvable to the version they cited).

State (the engine may only raise, supersede or reopen; contracts.states decides targets):
- not seen before: raised if the rule raised it; a finding already answered at the cutoff
  is simply not raised (8.5 suppression).
- open/accepted/edited: stays, unless the finding is now answered or gone -> SUPERSEDED
  (Tier 1 superseded still blocks closure until a clinician confirms).
- superseded: raised again -> REOPEN.
- resolved/dismissed by a human: stays, unless new evidence from a source not already cited
  on the disputed side appears -> REOPEN with ``new_evidence_since_decision``.
Adjudication (L2): a resolve decision naming the correct entry makes the other side's
statements inactive for THIS flag's detection, so restating the winning side cannot reopen.
Owner and ready_for_clinician of an existing flag are kept (reassignment is a human action).
"""

from __future__ import annotations

from datetime import datetime

from noteguard.contracts import ids, states
from noteguard.contracts.types import (
    Decision,
    DecisionAction,
    EngineTransition,
    EvidenceRole,
    Flag,
    FlagState,
    OwnerRouting,
    RuleDefinition,
    RuleId,
)

from .context import Candidate, Context, Item

_SIDES = frozenset({EvidenceRole.CLAIM, EvidenceRole.COUNTER_CLAIM})
#: Rules whose finding needs both sides of a disagreement present.
_TWO_SIDED = frozenset({RuleId.ALG_001, RuleId.DOSE_001})
_HUMAN_CLOSED = frozenset({FlagState.RESOLVED, FlagState.DISMISSED})


def _author(ctx: Context, source_id: str) -> str:
    return next(s.author_staff_id for s in ctx.snapshot.sources if s.source_id == source_id)


def route_owner(ctx: Context, rule: RuleDefinition, items: list[Item]) -> str:
    """8.6: Tier 1 -> responsible clinician (else attending); cross-source -> responsible
    clinician; single-source -> source-note owner (the uploader for external documents)."""
    if int(rule.default_tier) == 1 or rule.owner_routing in (OwnerRouting.RESPONSIBLE_CLINICIAN,
                                                             OwnerRouting.RESPONSIBLE_CLINICIAN_PLUS_PHARMACY):
        return ctx.tier1_owner
    sources = list(dict.fromkeys(i.source_id for i in items if i.source_id))
    about = next((i.source_id for i in items if i.role in (EvidenceRole.CLAIM, EvidenceRole.EXTRACTION_GAP)
                  and i.source_id), sources[0] if sources else None)
    if about is None:
        return ctx.tier1_owner
    if rule.owner_routing is OwnerRouting.SINGLE_SOURCE_OWNER_ELSE_RESPONSIBLE and len(sources) > 1:
        return ctx.tier1_owner
    return _author(ctx, about)


def affected(ctx: Context, rule: RuleDefinition, items: list[Item], owner: str) -> tuple[str, ...]:
    people = {_author(ctx, i.source_id) for i in items if i.source_id}
    if rule.owner_routing is OwnerRouting.RESPONSIBLE_CLINICIAN_PLUS_PHARMACY:
        people |= ctx.pharmacists()
    return tuple(sorted(people - {owner}))


def _unmatched(fresh: list[Item], prior: list[Item]) -> list[Item]:
    pool = [p.match_key for p in prior]
    out = []
    for f in fresh:
        if f.match_key in pool:
            pool.remove(f.match_key)
        else:
            out.append(f)
    return out


def _source_changed(ctx: Context, items: list[Item]) -> bool:
    for i in items:
        if i.doc is None or i.ev.source_version_id is None:
            continue
        latest = ctx.latest_in_scope(i.source_id)
        if latest is not None and latest.svid != i.ev.source_version_id and latest.version.version > i.doc.version.version:
            return True
    return False


def _adjudicate(ctx: Context, cand: Candidate, prior: Flag | None, decisions: list[Decision]) -> Candidate | None:
    """Drop statements a clinician adjudicated as the losing side of THIS flag (L2)."""
    if prior is None:
        return cand
    rulings = [d for d in decisions if d.action is DecisionAction.RESOLVE and d.adjudicated_evidence]
    if not rulings:
        return cand
    ruling = max(rulings, key=lambda d: d.at)
    prior_items = [ctx.resolve(cand.rule_id, cand.subject_key, e) for e in prior.evidence]
    refs = {(r.source_version_id, r.start, r.end) for r in ruling.adjudicated_evidence}
    winners = {i.role for i in prior_items if (i.ev.source_version_id, i.ev.start, i.ev.end) in refs}
    losing = {(i.source_id, i.sig) for i in prior_items if i.role in _SIDES and i.role not in winners}
    if not winners or not losing:
        return cand
    kept = [i for i in cand.items if not (i.role in _SIDES and (i.source_id, i.sig) in losing)]
    for i in cand.items:
        if i not in kept and i.stmt is not None:
            for f in i.stmt.facts:
                f.adjudicated = True
    if cand.rule_id in _TWO_SIDED and not ({EvidenceRole.CLAIM, EvidenceRole.COUNTER_CLAIM} <= {i.role for i in kept}):
        return None
    return Candidate(cand.rule_id, cand.subject_key, kept, raised=cand.raised, reason=cand.reason,
                     question=cand.question)


def _build(ctx: Context, rule: RuleDefinition, fid: str, subject: str, items: list[Item], *, owner: str, state: FlagState,
           revision: int, evidence_revision: int, reason: str, question: str | None, created_at: datetime,
           first_run_id: str, run_id: str, ready: bool = False, new_evidence: bool = False,
           source_changed: bool = False, tier: int | None = None) -> Flag:
    items = sorted(items, key=ctx.order_key)
    reg = ctx.bundle.registry.registry_version
    return Flag(
        flag_id=fid, tier=tier if tier is not None else rule.default_tier, category=rule.category, title=rule.title,
        reason=reason, evidence=tuple(i.ev for i in items), owner_staff_id=owner,
        check_version=ids.check_version(ctx.bundle.ruleset.ruleset_version, rule.rule_id.value, rule.version, reg),
        created_at=created_at, rule_id=rule.rule_id, lens=rule.lens, subject_key=subject, state=state,
        revision=revision, evidence_revision=evidence_revision,
        affected_contributor_ids=affected(ctx, rule, items, owner), question=question, ready_for_clinician=ready,
        new_evidence_since_decision=new_evidence, source_changed_since_flag=source_changed,
        first_run_id=first_run_id, last_run_id=run_id)


def merge(ctx: Context, rule: RuleDefinition, fid: str, subject: str, prior: Flag | None, cand: Candidate | None,
          run_id: str, evaluated_at: datetime) -> Flag | None:
    if prior is None:
        if cand is None or not cand.raised:
            return None  # never seen and answered at the cutoff: suppression, not closure (8.5)
        return _build(ctx, rule, fid, subject, cand.items, owner=route_owner(ctx, rule, cand.items),
                      state=states.engine_target(EngineTransition.RAISE, None), revision=1, evidence_revision=1,
                      reason=cand.reason, question=cand.question, created_at=evaluated_at, first_run_id=run_id,
                      run_id=run_id, source_changed=_source_changed(ctx, cand.items))
    prior_items = [ctx.resolve(rule.rule_id, subject, e) for e in prior.evidence]
    raised = cand is not None and cand.raised
    new = _unmatched(cand.items, prior_items) if cand is not None else []
    transition: EngineTransition | None = None
    new_evidence = prior.new_evidence_since_decision
    if prior.state in _HUMAN_CLOSED:
        cited_sources = {i.source_id for i in prior_items}
        contradicting = [i for i in new if i.role in _SIDES and i.source_id not in cited_sources]
        if raised and contradicting:
            transition, new_evidence = EngineTransition.REOPEN, True
        else:
            new = []  # restating what a human already decided changes nothing
    elif prior.state is FlagState.SUPERSEDED:
        if raised:
            transition = EngineTransition.REOPEN
    elif not raised:
        transition = EngineTransition.SUPERSEDE
    state = states.engine_target(transition, prior.state) if transition else prior.state
    evidence_revision = prior.evidence_revision + (1 if new else 0)
    items = prior_items + [i.with_revision(evidence_revision) for i in new]
    changed = _source_changed(ctx, items)
    bump = bool(new) or transition is not None or (changed and not prior.source_changed_since_flag)
    reason = cand.reason if (cand is not None and raised and new) else prior.reason
    return _build(ctx, rule, fid, subject, items, owner=prior.owner_staff_id, state=state,
                  revision=prior.revision + (1 if bump else 0), evidence_revision=evidence_revision, reason=reason,
                  question=prior.question or (cand.question if cand else None), created_at=prior.created_at,
                  first_run_id=prior.first_run_id, run_id=run_id, ready=prior.ready_for_clinician,
                  new_evidence=new_evidence, source_changed=prior.source_changed_since_flag or changed,
                  tier=int(prior.tier))


def orchestrate(ctx: Context, candidates: list[Candidate], run_id: str, evaluated_at: datetime) -> list[Flag]:
    enc = ctx.encounter.encounter_id
    grouped: dict[str, Candidate] = {}
    for c in candidates:
        fid = ids.flag_id(c.rule_id.value, enc, c.subject_key)
        if fid in grouped:  # same subject twice (e.g. two identical unparsed-dose lines): one flag
            g = grouped[fid]
            grouped[fid] = Candidate(c.rule_id, c.subject_key, g.items + c.items, raised=g.raised or c.raised,
                                     reason=g.reason or c.reason, question=g.question or c.question)
        else:
            grouped[fid] = c
    prior = {f.flag_id: f for f in ctx.snapshot.prior_flags}
    decisions: dict[str, list[Decision]] = {}
    for d in ctx.snapshot.decisions:
        decisions.setdefault(d.flag_id, []).append(d)
    out: dict[str, Flag] = {}
    for fid, cand in grouped.items():
        rule = ctx.rules[cand.rule_id]
        p = prior.get(fid)
        adjusted = _adjudicate(ctx, cand, p, decisions.get(fid, []))
        flag = merge(ctx, rule, fid, cand.subject_key, p, adjusted, run_id, evaluated_at)
        if flag is not None:
            out[fid] = flag
    for fid, p in prior.items():
        if fid in out:
            continue
        rule = ctx.rules.get(p.rule_id)
        if rule is None or not rule.enabled:
            out[fid] = p  # not evaluated by this ruleset: carried unchanged
        else:
            out[fid] = merge(ctx, rule, fid, p.subject_key, p, None, run_id, evaluated_at)
    return sorted(out.values(), key=lambda f: (int(f.tier), f.rule_id.value, f.subject_key))
