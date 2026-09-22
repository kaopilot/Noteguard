"""Completeness rules.

DOSE-002 (Tier 3, L4): every number + registry dose unit that is not attached to a parsed
regimen (drug term, then separators / change language / "to", "at", "of", "dose", then the
dose) raises a review item for its statement. A dose the checker did not parse is never a
pass. Subject: unparsed_dose@source:<source_id>:<first 16 hex of sha256(quote)>.

PEND-001 (Tier 2): a statement with a live pending cue naming a registry test or analyte,
missing an explicit owner (registry OWNER cue) OR explicit timing (registry TIMING cue) in
the same statement or in a later statement that names the same subject. Both present: not
raised. Owner: single source -> its author; cross-source -> responsible clinician.

PDF-001 (Tier 2): an in-scope source whose extraction status is not complete/not_applicable.
Evidence: one extraction_gap anchor per page with no text layer. Closed only by a human
decision (manual review / OCR done).

OWN-001 (Tier 1): no responsible clinician recorded on the encounter. Cites the structured
field with one encounter_record evidence item (no span); owner = the attending (8.6).
"""

from __future__ import annotations

from noteguard.contracts.types import CueKind, EvidenceRole, FactType, RecordField, RuleId

from ..context import Candidate, Context
from ..extract import Stmt
from .common import items, more, render

OWN_SUBJECT = "encounter:responsible_clinician"


def unparsed_dose(ctx: Context) -> list[Candidate]:
    rule_id = RuleId.DOSE_002
    rule = ctx.rules[rule_id]
    out = []
    for f in ctx.facts:
        if f.fact_type is FactType.UNPARSED_DOSE:
            ev = items(ctx, rule_id, [f.stmt], EvidenceRole.CLAIM, f.subject_key)
            reason = render(rule.reason_template, source_label=ctx.source_label(f.doc.source_id),
                            claim_quote=ctx.quoted(f.stmt.quote))
            out.append(Candidate(rule_id, f.subject_key, ev, reason=reason))
    return out


def _after(ctx: Context, st: Stmt) -> list[Stmt]:
    return [s for d in ctx.docs for s in d.stmts if (d.order, s.idx) > (st.doc.order, st.idx)]


def pending(ctx: Context) -> list[Candidate]:
    rule_id = RuleId.PEND_001
    rule = ctx.rules[rule_id]
    facts = [f for f in ctx.facts if f.fact_type is FactType.PENDING_ACTION]
    out = []
    for key in dict.fromkeys(f.subject_key for f in facts):
        missing: list[tuple[Stmt, bool, bool]] = []
        answered: list[Stmt] = []
        linked_used: list[Stmt] = []
        for p in (f for f in facts if f.subject_key == key):
            owner, timing = p.stmt.has(CueKind.OWNER), p.stmt.has(CueKind.TIMING)
            for s in _after(ctx, p.stmt):
                if not any(m.key == key and not m.negated for m in s.mentions):
                    continue
                o, t = s.has(CueKind.OWNER), s.has(CueKind.TIMING)
                if (o and not owner) or (t and not timing):
                    linked_used.append(s)
                owner, timing = owner or o, timing or t
            if owner and timing:
                answered.append(p.stmt)
            else:
                missing.append((p.stmt, owner, timing))
        if missing:
            need_owner = any(not o for _, o, _ in missing)
            need_timing = any(not t for _, _, t in missing)
            label = "owner or timing" if need_owner and need_timing else ("owner" if need_owner else "timing")
            ev = items(ctx, rule_id, [s for s, _, _ in missing], EvidenceRole.CLAIM, key)
            first = missing[0][0]
            reason = render(rule.reason_template, source_label=ctx.source_label(first.doc.source_id),
                            claim_quote=ctx.quoted(first.quote), missing_label=label) + more(len(ev))
            out.append(Candidate(rule_id, key, ev, reason=reason))
        elif answered:
            seen: set = set()
            ev = items(ctx, rule_id, answered, EvidenceRole.CLAIM, key, seen)
            ev += items(ctx, rule_id, [s for s in linked_used if (s.key, EvidenceRole.CLAIM) not in seen],
                        EvidenceRole.SUPPRESSOR, key, seen)
            out.append(Candidate(rule_id, key, ev, raised=False))
    return out


def unreadable(ctx: Context) -> list[Candidate]:
    rule_id = RuleId.PDF_001
    rule = ctx.rules[rule_id]
    out = []
    for d in ctx.docs:
        if not d.readable:
            reason = render(rule.reason_template, source_label=ctx.source_label(d.source_id),
                            extraction_status=d.extraction.status.value)
            out.append(Candidate(rule_id, f"source:{d.source_id}", ctx.gap_items(d), reason=reason))
    return out


def no_responsible_clinician(ctx: Context) -> list[Candidate]:
    rule_id = RuleId.OWN_001
    if ctx.encounter.responsible_clinician_id is not None:
        return []
    reason = render(ctx.rules[rule_id].reason_template)
    return [Candidate(rule_id, OWN_SUBJECT, [ctx.record_item(RecordField.ENCOUNTER_RESPONSIBLE_CLINICIAN)],
                      reason=reason)]
