"""One evaluation: the in-scope documents and facts at a cutoff, plus helpers every rule,
the flag orchestrator, the bubble builder and the summary builder share. Pure: everything
is derived from the snapshot and bundle passed in."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from noteguard.contracts import ids
from noteguard.contracts.types import (
    Encounter,
    EncounterSnapshot,
    Evidence,
    EvidenceRole,
    FactType,
    RecordField,
    Role,
    RuleDefinition,
    RuleId,
    RulesetBundle,
    Staff,
)

from .diff import difference
from .extract import Doc, Extractor, Fact, Stmt, in_scope
from .registry import Lexicon

#: Display time zone (Asia/Singapore, UTC+8, no daylight saving). A fixed offset keeps the
#: engine free of tz-database file reads.
SGT = timezone(timedelta(hours=8))

#: Fact types each rule reads, and whether they must also match the flag's subject key.
#: Used to decide whether a cited statement's normalised facts still hold on a rerun (8.4).
_RULE_FACTS: dict[RuleId, tuple[frozenset[FactType], bool]] = {
    RuleId.CRIT_001: (frozenset({FactType.OBSERVATION, FactType.RESPONSE}), True),
    RuleId.ALG_001: (frozenset({FactType.ALLERGY}), False),
    RuleId.DOSE_001: (frozenset({FactType.MEDICATION}), True),
    RuleId.DOSE_002: (frozenset({FactType.UNPARSED_DOSE}), False),
    RuleId.PEND_001: (frozenset({FactType.PENDING_ACTION}), True),
    RuleId.DIFF_001: (frozenset({FactType.CLINICAL_STATUS, FactType.OBSERVATION}), False),
}


@dataclass(eq=False)
class Item:
    """One evidence item plus what rerun matching needs (8.4, README convention 7)."""

    ev: Evidence
    source_id: str | None
    sig: tuple
    doc: Doc | None = None
    stmt: Stmt | None = None

    @property
    def role(self) -> EvidenceRole:
        return self.ev.role_in_flag

    @property
    def match_key(self) -> tuple:
        return (self.source_id, self.role.value, self.sig)

    def with_revision(self, rev: int) -> "Item":
        return Item(ev=self.ev.model_copy(update={"evidence_revision": rev}), source_id=self.source_id,
                    sig=self.sig, doc=self.doc, stmt=self.stmt)


@dataclass(eq=False)
class Candidate:
    """What a rule found for one subject. ``raised`` False = the finding is answered at the
    cutoff (suppressed); its items then include the suppressor evidence."""

    rule_id: RuleId
    subject_key: str
    items: list[Item]
    raised: bool = True
    reason: str = ""
    question: str | None = None


@dataclass(eq=False)
class Context:
    snapshot: EncounterSnapshot
    bundle: RulesetBundle
    cutoff: datetime
    lex: Lexicon = field(init=False)
    extractor: Extractor = field(init=False)
    docs: list[Doc] = field(init=False)
    facts: list[Fact] = field(init=False)
    changes: list = field(init=False)

    def __post_init__(self) -> None:
        self.lex = Lexicon(self.bundle.registry)
        self.extractor = Extractor(self.bundle, self.lex)
        self.docs = [self.extractor.doc(s, v, e, i) for i, (s, v, e) in enumerate(in_scope(self.snapshot, self.cutoff))]
        self.facts = [f for d in self.docs for st in d.stmts for f in st.facts]
        self.changes = difference(self.docs)
        self._staff = {s.staff_id: s for s in self.snapshot.staff}
        self._sources = {s.source_id: s for s in self.snapshot.sources}
        self._versions = {v.source_version_id: v for v in self.snapshot.versions}
        self._ext = {e.source_version_id: e for e in self.snapshot.extractions}
        self._by_svid = {d.svid: d for d in self.docs}
        self.rules: dict[RuleId, RuleDefinition] = {r.rule_id: r for r in self.bundle.ruleset.rules}

    # --- people and routing ------------------------------------------------------------

    @property
    def encounter(self) -> Encounter:
        return self.snapshot.encounter

    @property
    def tier1_owner(self) -> str:
        """8.6: responsible clinician; if none is recorded, the attending (never unassigned)."""
        e = self.encounter
        return e.responsible_clinician_id or e.attending_clinician_id

    def staff(self, staff_id: str) -> Staff | None:
        return self._staff.get(staff_id)

    def staff_name(self, staff_id: str) -> str:
        s = self._staff.get(staff_id)
        return s.display_name if s else "unlisted staff member"

    def pharmacists(self) -> set[str]:
        """Care-team members whose system role is pharmacist, active at the cutoff."""
        out = set()
        for m in self.snapshot.memberships:
            s = self._staff.get(m.staff_id)
            active = m.valid_from <= self.cutoff and (m.valid_to is None or m.valid_to > self.cutoff)
            if s and active and s.role is Role.PHARMACIST:
                out.add(s.staff_id)
        return out

    # --- labels ------------------------------------------------------------------------

    @staticmethod
    def hhmm(t: datetime) -> str:
        return t.astimezone(SGT).strftime("%H:%M")

    def source_label(self, source_id: str) -> str:
        s = self._sources[source_id]
        return f"{s.title} ({self.staff_name(s.author_staff_id)}, {self.hhmm(s.source_time)})"

    @staticmethod
    def quoted(text: str) -> str:
        return '"' + text + '"'

    # --- documents for any cited version (rerun citations may be out of scope) ----------

    def doc_for(self, svid: str) -> Doc:
        d = self._by_svid.get(svid)
        if d is None:
            v = self._versions[svid]
            d = self.extractor.doc(self._sources[v.source_id], v, self._ext[svid], -1)
            self._by_svid[svid] = d
        return d

    def latest_in_scope(self, source_id: str) -> Doc | None:
        return next((d for d in self.docs if d.source_id == source_id), None)

    # --- evidence ----------------------------------------------------------------------

    def page_of(self, doc: Doc, start: int) -> int | None:
        pages = doc.extraction.pages
        if not pages:
            return None
        for p in pages:
            if p.start <= start < max(p.end, p.start + 1):
                return p.page
        return pages[-1].page

    def sig(self, rule_id: RuleId, stmt: Stmt, subject_key: str) -> tuple:
        types, by_subject = _RULE_FACTS.get(rule_id, (frozenset(FactType), False))
        facts = [f for f in stmt.facts if f.fact_type in types and (not by_subject or f.subject_key == subject_key)]
        return tuple(sorted(f.signature() for f in facts)) or (("text", stmt.comparable),)

    def span_item(self, rule_id: RuleId, stmt: Stmt, role: EvidenceRole, subject_key: str) -> Item:
        doc = stmt.doc
        ev = Evidence(note_version_id=doc.svid, start=stmt.start, end=stmt.end, page=self.page_of(doc, stmt.start),
                      quote=stmt.quote, quote_sha256=ids.quote_sha256(stmt.quote), role_in_flag=role)
        return Item(ev=ev, source_id=doc.source_id, sig=self.sig(rule_id, stmt, subject_key), doc=doc, stmt=stmt)

    def gap_items(self, doc: Doc, role: EvidenceRole = EvidenceRole.EXTRACTION_GAP) -> list[Item]:
        """One anchor per unread page (start == end == page start, quote ""); README convention 1."""
        pages = doc.extraction.pages
        unread = [p for p in pages if p.char_count == 0] or list(pages[:1])
        out = []
        for p in unread or [None]:
            start = p.start if p else 0
            ev = Evidence(note_version_id=doc.svid, start=start, end=start, page=p.page if p else None, quote="",
                          quote_sha256=ids.quote_sha256(""), role_in_flag=role)
            out.append(Item(ev=ev, source_id=doc.source_id, sig=(("page", p.page if p else 0),), doc=doc))
        return out

    def record_item(self, field_: RecordField) -> Item:
        ev = Evidence(note_version_id=None, start=0, end=0, page=None, quote="", quote_sha256=ids.quote_sha256(""),
                      role_in_flag=EvidenceRole.ENCOUNTER_RECORD, record_field=field_)
        return Item(ev=ev, source_id=None, sig=(("record", field_.value),))

    def resolve(self, rule_id: RuleId, subject_key: str, ev: Evidence) -> Item:
        """Rebuild an Item for evidence cited by an earlier run (possibly an older version)."""
        if ev.source_version_id is None:
            return Item(ev=ev, source_id=None, sig=(("record", ev.record_field.value if ev.record_field else ""),))
        doc = self.doc_for(ev.source_version_id)
        if ev.role_in_flag is EvidenceRole.EXTRACTION_GAP or ev.start == ev.end:
            return Item(ev=ev, source_id=doc.source_id, sig=(("page", ev.page or 0),), doc=doc)
        stmt = next((s for s in doc.stmts if (s.start, s.end) == (ev.start, ev.end)), None)
        if stmt is None:
            return Item(ev=ev, source_id=doc.source_id, sig=(("span", ev.start, ev.end, ev.quote_sha256),), doc=doc)
        return Item(ev=ev, source_id=doc.source_id, sig=self.sig(rule_id, stmt, subject_key), doc=doc, stmt=stmt)

    def order_key(self, item: Item) -> tuple:
        if item.doc is None:
            return (0, "", "", "", 0, item.role.value)
        d = item.doc
        return (1, d.source.source_time.isoformat(), d.version.received_at.isoformat(), d.svid, item.ev.start,
                item.role.value)
