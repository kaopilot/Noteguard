"""Question bubbles (Section 8.8). Deterministic, from the question catalog in the ruleset.

Each answer is exactly one of the five BubbleStatus values. "Not documented in the supplied
sources" is a claim about a SEARCH: it is only possible when every in-scope source is fully
extracted; otherwise the answer is incomplete_extraction naming the unread sources. The
contract's AbsenceFinding refuses any other combination.

Triggers: flag_rule templates -> one bubble per UNRESOLVED flag of that rule;
critical_observation templates -> one bubble per critical analyte in scope, linked to that
analyte's CRIT-001 flag in any state. Absence search: every registry term must be named
(not negated) and, if the template lists cues, at least one live cue must be present.
Response searches over a critical observation use exactly the CRIT-001 suppressor test
(8.5), so earlier, carried-forward and negated lines never count. Flag-rule searches look at
the trigger statement and later statements only (a linked later statement, as PEND-001).
"""

from __future__ import annotations

from noteguard.contracts import ids, states
from noteguard.contracts.types import (
    AbsenceFinding,
    BubbleAnswerMode,
    BubbleStatus,
    BubbleTriggerKind,
    CheckRunResult,
    CueKind,
    EvidenceRole,
    Flag,
    QuestionBubble,
    QuestionTemplate,
    RuleId,
    SearchedSource,
)

from .context import Context, Item
from .extract import Stmt
from .rules.crit import CritState, critical_states

_CUE_PREFIX = "cue:"
_SUBJECT = "{subject}"
_RESPONSE_CUES = frozenset({CueKind.RESPONSE_REVIEW, CueKind.RESPONSE_REPEAT, CueKind.RESPONSE_TREATMENT,
                            CueKind.RESPONSE_ESCALATION, CueKind.RESPONSE_TRANSFER})

U_CONFLICT = ("The supplied sources disagree. Only a clinician's decision can settle which entry is correct; the "
              "checker does not choose between sources.")
U_DOCUMENTED = ("Documented in the cited source. The checker matched wording only and has not verified the clinical "
                "content.")
U_REVIEW = {
    RuleId.PDF_001: "The checker cannot answer this from the supplied text; a person needs to check the document.",
    RuleId.DIFF_001: ("The checker cannot tell whether a repeated statement is current; the note's author or the "
                      "responsible clinician needs to confirm."),
    RuleId.OWN_001: "The care-team record names no responsible clinician; only a person can assign one.",
    RuleId.DOSE_002: ("The checker could not attach this dose to a medication; the note's author needs to confirm "
                      "which medication it belongs to."),
}
U_REVIEW_DEFAULT = "Only a person can answer this from the supplied sources."


def _absent_note(ctx: Context) -> str:
    return (f"Searched {len(ctx.docs)} supplied sources up to {ctx.hhmm(ctx.cutoff)} for the listed terms and found no "
            "matching entry. This describes the supplied record only, not what took place.")


def _incomplete_note(ctx: Context, unread: list) -> str:
    n = len(unread)
    labels = "; ".join(ctx.source_label(d.source_id) for d in unread)
    return (f"{n} in-scope source{'s' if n > 1 else ''} could not be read: {labels}. The answer stays incomplete "
            f"until {'it is' if n == 1 else 'they are'} reviewed manually or by approved OCR.")


def _terms(t: QuestionTemplate, subject: str) -> tuple[list[str], list[str], list[CueKind]]:
    resolved = [subject if k == _SUBJECT else k for k in t.search_term_keys] or [subject]
    keys = [k for k in resolved if not k.startswith(_CUE_PREFIX)]
    cues = [CueKind(k[len(_CUE_PREFIX):]) for k in resolved if k.startswith(_CUE_PREFIX)]
    return resolved, keys, cues


def _matching(stmts: list[Stmt], keys: list[str], cues: list[CueKind]) -> list[Stmt]:
    return [st for st in stmts
            if all(any(m.key == k and not m.negated for m in st.mentions) for k in keys)
            and (not cues or any(st.has(c) for c in cues))]


def _values(ctx: Context, subject: str, about: Item | None) -> dict[str, str]:
    v = dict(subject_label=ctx.lex.label(subject))
    if about is not None and about.source_id is not None:
        v.update(source_label=ctx.source_label(about.source_id), source_time_label=ctx.hhmm(about.doc.time))
        if about.stmt is not None:
            v.update(claim_quote=ctx.quoted(about.stmt.quote))
    return v


def _search(ctx: Context, t: QuestionTemplate, subject: str, triggers: list[Item], scope: list[Stmt],
            answered: list[Stmt] | None) -> tuple[BubbleStatus, list[Item], AbsenceFinding | None]:
    resolved, keys, cues = _terms(t, subject)
    found = answered if answered is not None else _matching(scope, keys, cues)
    trigger_stmts = {i.stmt for i in triggers}
    if found:
        if trigger_stmts & set(found):
            return BubbleStatus.DOCUMENTED, triggers, None
        seen: set = set()
        extra = [ctx.span_item(RuleId.CRIT_001, st, EvidenceRole.SUPPRESSOR, subject) for st in found
                 if not (st in seen or seen.add(st))]
        return BubbleStatus.DOCUMENTED, triggers + extra, None
    unread = [d for d in ctx.docs if not d.readable]
    status = BubbleStatus.INCOMPLETE_EXTRACTION if unread else BubbleStatus.NOT_DOCUMENTED_IN_SUPPLIED_SOURCES
    gaps = [ctx.gap_items(d)[0] for d in unread]
    absence = AbsenceFinding(
        question_template_id=t.template_id, terms_searched=tuple(resolved), registry_version=ctx.lex.version,
        sources_searched=tuple(SearchedSource(note_version_id=d.svid, extraction_status=d.extraction.status)
                               for d in ctx.docs),
        cutoff=ctx.cutoff, status=status)
    return status, triggers + gaps, absence


def _bubble(ctx: Context, t: QuestionTemplate, subject: str, status: BubbleStatus, items: list[Item], note: str,
            values: dict[str, str], flag: Flag | None, absence: AbsenceFinding | None) -> QuestionBubble:
    items = sorted(items, key=ctx.order_key)
    return QuestionBubble(
        bubble_id=ids.bubble_id(t.template_id, ctx.encounter.encounter_id, subject), question_template_id=t.template_id,
        question=t.text.format_map(values), subject_key=subject, status=status, evidence=tuple(i.ev for i in items),
        cutoff=ctx.cutoff, uncertainty_note=note, flag_id=flag.flag_id if flag else None, absence=absence, rank=t.rank)


def _flag_bubble(ctx: Context, t: QuestionTemplate, f: Flag) -> QuestionBubble:
    cited = [ctx.resolve(f.rule_id, f.subject_key, e) for e in f.evidence]
    about = next((i for i in cited if i.role in (EvidenceRole.CLAIM, EvidenceRole.EXTRACTION_GAP)), None)
    if about is None and cited:
        about = cited[0]
    values = _values(ctx, f.subject_key, about)
    if t.answer_mode is BubbleAnswerMode.CONFLICT_STATE:
        return _bubble(ctx, t, f.subject_key, BubbleStatus.CONFLICTING, cited, U_CONFLICT, values, f,
                       None)
    if t.answer_mode is BubbleAnswerMode.HUMAN_REVIEW:
        return _bubble(ctx, t, f.subject_key, BubbleStatus.REQUIRES_HUMAN_REVIEW, cited,
                       U_REVIEW.get(f.rule_id, U_REVIEW_DEFAULT), values, f, None)
    claims = [i for i in cited if i.role is EvidenceRole.CLAIM and i.stmt is not None]
    triggers = [ctx.span_item(f.rule_id, i.stmt, EvidenceRole.TRIGGER, f.subject_key) for i in claims]
    first = min((i.stmt for i in claims if i.stmt.doc.order >= 0), key=lambda s: (s.doc.order, s.idx), default=None)
    scope = [s for d in ctx.docs for s in d.stmts if first is None or (d.order, s.idx) >= (first.doc.order, first.idx)]
    status, items, absence = _search(ctx, t, f.subject_key, triggers, scope, None)
    return _bubble(ctx, t, f.subject_key, status, items, _note(ctx, status), values, f, absence)


def _note(ctx: Context, status: BubbleStatus) -> str:
    if status is BubbleStatus.DOCUMENTED:
        return U_DOCUMENTED
    if status is BubbleStatus.INCOMPLETE_EXTRACTION:
        return _incomplete_note(ctx, [d for d in ctx.docs if not d.readable])
    return _absent_note(ctx)


def _crit_bubble(ctx: Context, t: QuestionTemplate, st: CritState, flag: Flag | None) -> QuestionBubble:
    subject = st.analyte
    _, _, cues = _terms(t, subject)
    response_search = bool(set(cues) & _RESPONSE_CUES)
    answered = None
    triggers_f = st.triggers
    if response_search:
        triggers_f = st.unacknowledged or st.triggers
        answered = [] if st.unacknowledged else st.suppressors
    seen: set = set()
    triggers = [ctx.span_item(RuleId.CRIT_001, f.stmt, EvidenceRole.TRIGGER, subject) for f in triggers_f
                if not (f.stmt in seen or seen.add(f.stmt))]
    scope = [s for d in ctx.docs for s in d.stmts]
    status, items, absence = _search(ctx, t, subject, triggers, scope, answered)
    values = _values(ctx, subject, triggers[0] if triggers else None)
    return _bubble(ctx, t, subject, status, items, _note(ctx, status), values, flag, absence)


def answer(ctx: Context, result: CheckRunResult) -> tuple[QuestionBubble, ...]:
    out: list[QuestionBubble] = []
    crit = None
    for t in ctx.bundle.ruleset.question_templates:
        if t.trigger.kind is BubbleTriggerKind.FLAG_RULE:
            for f in result.flags:
                if f.rule_id is t.trigger.rule_id and states.is_unresolved(f.tier, f.state):
                    out.append(_flag_bubble(ctx, t, f))
        elif t.trigger.kind is BubbleTriggerKind.CRITICAL_OBSERVATION:
            crit = critical_states(ctx) if crit is None else crit
            for analyte, st in crit.items():
                if not st.triggers or (t.trigger.analyte_keys and analyte not in t.trigger.analyte_keys):
                    continue
                flag = next((f for f in result.flags if f.rule_id is RuleId.CRIT_001 and f.subject_key == analyte), None)
                out.append(_crit_bubble(ctx, t, st, flag))
        else:
            raise NotImplementedError(f"B1: bubble trigger {t.trigger.kind.value} not built")
    return tuple(sorted(out, key=lambda b: (b.rank, b.subject_key)))
