"""Per-page-load workspace store (B2; OPEN-3, Section 6.3).

SINGLE PROCESS, IN MEMORY (documented decision): each POST /api/workspaces creates a fresh
workspace seeded with the synthetic ENC-A1/ENC-B1/ENC-C1 case, keyed by the sha256 of a random
token that lives only in the client's JS memory (X-Workspace-Token). Reset deletes it; it
expires after Settings.workspace_ttl_s; a server restart clears everything. Nothing clinical is
written to disk. Production replaces this with Postgres + RLS.

STORE-LAYER AUTHORISATION (L6/L7): every public method that reads or mutates encounter data
takes an AuthContext and re-checks, on the workspace's own copy of the encounter, that the
workspace belongs to the actor, that the actor is an active care-team member (else 404) and
that the role/relation/tier allows the action (else 403), whatever the route layer did.

Clinical content (note text, PDF bytes, rationale text) is held here only. It never reaches a
log, an audit event or an error body. SourceVersions are immutable: new content = new row.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from noteguard.contracts import ids, permissions, states
from noteguard.contracts.api_models import (
    AddPdfSourceForm,
    AddTextSourceRequest,
    BubbleList,
    ChangeView,
    CheckRunView,
    DocumentTokenView,
    EncounterListItem,
    EncounterView,
    FeedbackRequest,
    FlagDetail,
    FlagRevision,
    GlanceView,
    SourceText,
    SourceView,
)
from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.log_allowlist import LogEvent
from noteguard.contracts.states import InvalidTransition
from noteguard.contracts.types import (
    AIDraftStatus,
    RuleId,
    AuditAction,
    AuditOutcome,
    AuditTargetType,
    CheckRunResult,
    ClosureStatus,
    ClosureView,
    Decision,
    DecisionAction,
    DecisionRequest,
    EditField,
    FlagState,
    Role,
    Tier,
    EncounterSnapshot,
    FeedbackEvent,
    Flag,
    QuestionBubble,
    ReasonCode,
    Source,
    SourceType,
    SourceVersion,
    Staff,
    StaleRevision,
    Summary,
    TextExtraction,
    WorkspaceInfo,
)

from . import authz, views
from .audit import AuditLog
from .authz import AuthContext, EncounterFacts
from .engine_seam import EngineSeam
from .errors import ApiError
from .logs import log_event
from .seed import Seed
from .settings import Settings, utcnow
from noteguard.intake import pdf as intake_pdf
from noteguard.intake.text import TEXT_MEDIA_TYPE, text_extraction

A = permissions.PermissionAction
D = DecisionAction
_RULE_VERSION = re.compile(r";rule@[A-Z]+-\d{3}\.(\d+);")
_RULESET_VERSION = re.compile(r"^ruleset@([^;]+);")


def _h(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AggregateRow:
    """One flag, stripped for the aggregate view (B4): no ids of any kind, no text."""

    rule_id: RuleId
    tier: Tier
    state: FlagState
    created_at: datetime
    owner_role: Role | None
    first_decision_at: datetime | None  # owner/clinician response time = first_decision_at - created_at
    disposition: DecisionAction | None  # latest human decision, if any


@dataclass
class RunRecord:
    snapshot: EncounterSnapshot  # the engine input (prior flags as they were before this run)
    result: CheckRunResult
    changes: tuple[ChangeView, ...]
    cutoff: datetime
    source_seq: int  # workspace source sequence the run saw (staleness)


@dataclass
class EncounterState:
    base: EncounterSnapshot  # seed: clinic, patient, encounter, staff, memberships
    sources: dict[str, Source]
    versions: list[SourceVersion]
    extractions: dict[str, TextExtraction]
    blobs: dict[str, bytes]  # version id -> original PDF bytes
    idem: dict[str, str]  # idempotency key -> version id
    flags: dict[str, Flag] = field(default_factory=dict)  # current state, engine order
    revisions: dict[str, list[FlagRevision]] = field(default_factory=dict)
    decisions: list[Decision] = field(default_factory=list)  # append-only
    feedback: list[FeedbackEvent] = field(default_factory=list)  # append-only
    runs: list[RunRecord] = field(default_factory=list)
    source_seq: int = 0

    @property
    def facts(self) -> EncounterFacts:
        return EncounterFacts(self.base.encounter, self.base.memberships)

    @property
    def encounter_id(self) -> str:
        return self.base.encounter.encounter_id

    def snapshot(self) -> EncounterSnapshot:
        return self.base.model_copy(update=dict(
            sources=tuple(self.sources.values()), versions=tuple(self.versions),
            extractions=tuple(self.extractions.values()), prior_flags=tuple(self.flags.values()),
            decisions=tuple(self.decisions)))


@dataclass
class Workspace:
    workspace_id: str
    staff_id: str
    expires_at: datetime
    encounters: dict[str, EncounterState]


@dataclass
class _Session:
    staff_id: str
    expires_at: datetime


@dataclass
class _DocToken:
    staff_id: str
    workspace_hash: str
    encounter_id: str
    version_id: str
    expires_at: datetime


class WorkspaceStore:
    def __init__(self, *, settings: Settings, seed: Seed, audit: AuditLog, seam: EngineSeam) -> None:
        self._settings = settings
        self._seed = seed
        self._audit = audit
        self._seam = seam
        self._lock = threading.RLock()
        self._sessions: dict[str, _Session] = {}
        self._workspaces: dict[str, Workspace] = {}
        self._doc_tokens: dict[str, _DocToken] = {}

    # ------------------------------------------------------------------ identity
    def login(self, staff_id: str) -> tuple[str, Staff]:
        staff = self._seed.staff.get(staff_id)
        if staff is None:
            self._audit.record(AuditAction.SESSION_START, AuditTargetType.WORKSPACE, AuditOutcome.DENIED)
            raise ApiError(ErrorCode.UNAUTHENTICATED)
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[_h(token)] = _Session(staff.staff_id, utcnow() + timedelta(seconds=self._settings.session_ttl_s))
        self._audit.record(AuditAction.SESSION_START, AuditTargetType.WORKSPACE, AuditOutcome.SUCCESS, actor=staff)
        return token, staff

    def staff_for_session(self, token: str | None) -> Staff:
        with self._lock:
            s = self._sessions.get(_h(token)) if token else None
            if s is not None and s.expires_at <= utcnow():
                del self._sessions[_h(token)]  # type: ignore[arg-type]
                s = None
        if s is None:
            raise ApiError(ErrorCode.UNAUTHENTICATED)
        return self._seed.staff[s.staff_id]

    def logout(self, token: str | None) -> None:
        with self._lock:
            s = self._sessions.pop(_h(token), None) if token else None
        if s is not None:
            self._audit.record(AuditAction.SESSION_END, AuditTargetType.WORKSPACE, AuditOutcome.SUCCESS,
                               actor=self._seed.staff[s.staff_id])

    # ------------------------------------------------------------------ workspaces
    def _seed_state(self, snap: EncounterSnapshot) -> EncounterState:
        blobs = {v.source_version_id: self._seed.blobs[v.sha256] for v in snap.versions
                 if v.media_type == intake_pdf.PDF_MEDIA_TYPE and v.sha256 in self._seed.blobs}
        return EncounterState(base=snap.model_copy(update=dict(prior_flags=(), decisions=())),
                              sources={s.source_id: s for s in snap.sources}, versions=list(snap.versions),
                              extractions={e.source_version_id: e for e in snap.extractions}, blobs=blobs,
                              idem={v.idempotency_key: v.source_version_id for v in snap.versions})

    def create_workspace(self, staff: Staff) -> WorkspaceInfo:
        token = secrets.token_urlsafe(32)
        now = utcnow()
        ws = Workspace(workspace_id=ids.new_id(), staff_id=staff.staff_id,
                       expires_at=now + timedelta(seconds=self._settings.workspace_ttl_s),
                       encounters={s.encounter.encounter_id: self._seed_state(s) for s in self._seed.snapshots})
        with self._lock:
            self._workspaces[_h(token)] = ws
        self._audit.record(AuditAction.WORKSPACE_CREATE, AuditTargetType.WORKSPACE, AuditOutcome.SUCCESS, actor=staff,
                           target_id=ws.workspace_id)
        in_scope = tuple(eid for eid, st in ws.encounters.items() if self._may(staff, st, A.READ_ENCOUNTER, now))
        return WorkspaceInfo(workspace_token=token, encounter_ids=in_scope, expires_at=ws.expires_at)

    def resolve_workspace(self, staff: Staff, token: str | None) -> AuthContext:
        key = _h(token) if token else ""
        self._ws(staff, key)
        return AuthContext(staff=staff, workspace_id=self._workspaces[key].workspace_id, workspace_hash=key)

    def _ws(self, staff: Staff, key: str) -> Workspace:
        """Re-validates ownership and expiry on EVERY store call (a forged ctx gets nothing)."""
        with self._lock:
            ws = self._workspaces.get(key)
            if ws is None or ws.staff_id != staff.staff_id:
                raise ApiError(ErrorCode.WORKSPACE_REQUIRED)
            if ws.expires_at <= utcnow():
                ws.encounters.clear()  # drop clinical content; keep the tombstone for a clear 410
                raise ApiError(ErrorCode.WORKSPACE_EXPIRED)
            return ws

    def reset_workspace(self, ctx: AuthContext) -> None:
        ws = self._ws(ctx.staff, ctx.workspace_hash)
        now = utcnow()
        if not any(self._may(ctx.staff, st, A.RESET_WORKSPACE, now) for st in ws.encounters.values()):
            raise ApiError(ErrorCode.FORBIDDEN_ROLE)
        with self._lock:
            self._workspaces.pop(ctx.workspace_hash, None)
            for k in [k for k, t in self._doc_tokens.items() if t.workspace_hash == ctx.workspace_hash]:
                del self._doc_tokens[k]
        self._audit.record(AuditAction.WORKSPACE_RESET, AuditTargetType.WORKSPACE, AuditOutcome.SUCCESS,
                           actor=ctx.staff, target_id=ws.workspace_id)

    # ------------------------------------------------------------------ the store-layer gate
    @staticmethod
    def _may(staff: Staff, st: EncounterState, action: permissions.PermissionAction, now: datetime) -> bool:
        try:
            authz.check_encounter_action(staff, st.facts, action, now)
            return True
        except ApiError:
            return False

    def _gate(self, ctx: AuthContext, encounter_id: str, action: permissions.PermissionAction) -> EncounterState:
        ws = self._ws(ctx.staff, ctx.workspace_hash)
        st = ws.encounters.get(encounter_id)
        if st is None:
            self._audit.record(AuditAction.ACCESS_DENIED, AuditTargetType.ENCOUNTER, AuditOutcome.NOT_FOUND, actor=ctx.staff)
            raise ApiError(ErrorCode.NOT_FOUND)
        try:
            authz.check_encounter_action(ctx.staff, st.facts, action, utcnow())
        except ApiError as exc:
            outcome = AuditOutcome.NOT_FOUND if exc.code is ErrorCode.NOT_FOUND else AuditOutcome.DENIED
            self._audit.record(AuditAction.ACCESS_DENIED, AuditTargetType.ENCOUNTER, outcome, actor=ctx.staff,
                               target_id=encounter_id)
            raise
        return st

    # ------------------------------------------------------------------ encounters and sources
    def list_encounters(self, ctx: AuthContext) -> tuple[EncounterListItem, ...]:
        ws = self._ws(ctx.staff, ctx.workspace_hash)
        now = utcnow()
        return tuple(EncounterListItem(encounter_id=st.encounter_id, encounter_ref=st.base.encounter.encounter_ref,
                                       patient_label=st.base.patient.display_label, setting=st.base.encounter.setting,
                                       responsible_clinician_id=st.base.encounter.responsible_clinician_id)
                     for st in ws.encounters.values() if self._may(ctx.staff, st, A.READ_ENCOUNTER, now))

    def get_encounter(self, ctx: AuthContext, encounter_id: str) -> EncounterView:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        with self._lock:
            srcs = views.source_views(st.sources, st.versions, st.extractions)
        self._audit.record(AuditAction.ENCOUNTER_READ, AuditTargetType.ENCOUNTER, AuditOutcome.SUCCESS, actor=ctx.staff,
                           target_id=encounter_id)
        return EncounterView(encounter=st.base.encounter, patient_label=st.base.patient.display_label, staff=st.base.staff,
                             memberships=st.base.memberships, sources=srcs)

    def get_source_text(self, ctx: AuthContext, encounter_id: str, version_id: str) -> SourceText:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        ext = st.extractions.get(version_id)
        if ext is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return SourceText(note_version_id=ext.source_version_id, extraction_status=ext.status, text=ext.text,
                          pages=ext.pages)

    def add_text_source(self, ctx: AuthContext, encounter_id: str, req: AddTextSourceRequest) -> tuple[SourceView, bool]:
        st = self._gate(ctx, encounter_id, A.ADD_SOURCE)
        return self._add_version(ctx, st, req, SourceType.PASTED_TEXT, req.text.encode("utf-8"), TEXT_MEDIA_TYPE,
                                 lambda vid: text_extraction(vid, req.text))

    def add_pdf_source(self, ctx: AuthContext, encounter_id: str, form: AddPdfSourceForm,
                       data: bytes) -> tuple[SourceView, bool]:
        st = self._gate(ctx, encounter_id, A.ADD_SOURCE)
        try:
            intake_pdf.check_bytes(data, max_bytes=self._settings.pdf_max_bytes)
            self._check_source_meta(st, form, SourceType.PDF)  # refuse bad metadata before extracting
            result = intake_pdf.extract(data, max_pages=self._settings.pdf_max_pages,
                                        timeout_s=self._settings.pdf_extraction_timeout_s)
        except intake_pdf.PdfRejected as exc:
            raise ApiError(exc.code) from None
        view, created = self._add_version(ctx, st, form, SourceType.PDF, data, intake_pdf.PDF_MEDIA_TYPE,
                                          result.to_extraction)
        if result.timed_out:
            raise ApiError(ErrorCode.PDF_EXTRACTION_TIMEOUT)  # source RETAINED with status failed
        return view, created

    def _check_source_meta(self, st: EncounterState, meta, source_type: SourceType) -> Source | None:
        """Resolve the logical document a new version belongs to; refuse mismatched metadata."""
        author = self._seed.staff.get(meta.author_staff_id)
        if author is None or not authz.active_member(author, st.facts, utcnow()):
            raise ApiError(ErrorCode.VALIDATION_FAILED)  # accountable owner must be on the care team
        src = None
        if meta.source_id is not None:
            src = st.sources.get(meta.source_id)
            if src is None:
                raise ApiError(ErrorCode.NOT_FOUND)
        elif meta.external_id is not None:
            src = next((s for s in st.sources.values() if s.identifier_namespace == meta.identifier_namespace
                        and s.external_id == meta.external_id), None)
        if src is not None:
            sent_ns = "identifier_namespace" in meta.model_fields_set
            if (src.source_type != source_type or src.title != meta.title or src.discipline != meta.discipline
                    or src.author_staff_id != meta.author_staff_id or src.source_time != meta.source_time
                    or (sent_ns and src.identifier_namespace != meta.identifier_namespace)
                    or (meta.external_id is not None and meta.external_id != src.external_id)):
                raise ApiError(ErrorCode.VALIDATION_FAILED)
        return src

    def _add_version(self, ctx: AuthContext, st: EncounterState, meta, source_type: SourceType, data: bytes,
                     media_type: str, build_extraction) -> tuple[SourceView, bool]:
        with self._lock:
            src = self._check_source_meta(st, meta, source_type)
            sha = ids.sha256_hex(data)
            if src is None and meta.external_id is None:
                # No EMR id: the logical document is identified by its metadata + content, so an
                # identical re-post is a replay (no duplicate source), a different author/time is not.
                auto = "auto-" + ids.sha256_hex(ids.canonical_json([
                    source_type.value, meta.title, meta.discipline.value, meta.author_staff_id,
                    meta.source_time.isoformat(), sha]))[:32]
                src = next((s for s in st.sources.values() if s.identifier_namespace == meta.identifier_namespace
                            and s.external_id == auto), None)
            else:
                auto = None
            if src is not None:
                prev = max((v for v in st.versions if v.source_id == src.source_id), key=lambda v: v.version)
                if prev.sha256 == sha:  # replay of the current version: no new row
                    return views.source_view(src, prev, st.extractions[prev.source_version_id]), False
                version, supersedes = prev.version + 1, prev.source_version_id
                namespace, external_id = src.identifier_namespace, src.external_id
            else:
                version, supersedes = 1, None
                namespace, external_id = meta.identifier_namespace, meta.external_id or auto
            key = meta.idempotency_key or ids.idempotency_key(namespace, external_id, version, sha)
            if key in st.idem:
                existing = next(v for v in st.versions if v.source_version_id == st.idem[key])
                if existing.sha256 != sha:
                    raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return views.source_view(st.sources[existing.source_id], existing,
                                         st.extractions[existing.source_version_id]), False
            now = utcnow()
            if src is None:
                src = Source(source_id=ids.new_id(), encounter_id=st.encounter_id, source_system="noteguard-api",
                             identifier_namespace=namespace, external_id=external_id, source_type=source_type,
                             author_staff_id=meta.author_staff_id, discipline=meta.discipline, title=meta.title,
                             source_time=meta.source_time)
                st.sources[src.source_id] = src
            # version_time = received_at = server clock: this system recorded this version now (no backdating)
            v = SourceVersion(source_version_id=ids.new_id(), source_id=src.source_id, version=version, version_time=now,
                              received_at=now, sha256=sha, byte_length=len(data), media_type=media_type,
                              idempotency_key=key, supersedes_version_id=supersedes)
            ext = build_extraction(v.source_version_id)
            st.versions.append(v)
            st.extractions[v.source_version_id] = ext
            if media_type == intake_pdf.PDF_MEDIA_TYPE:
                st.blobs[v.source_version_id] = data
            st.idem[key] = v.source_version_id
            st.source_seq += 1
        self._audit.record(AuditAction.SOURCE_VERSION_ADDED, AuditTargetType.SOURCE_VERSION, AuditOutcome.SUCCESS,
                           actor=ctx.staff, target_id=v.source_version_id, hashes=(sha,))
        log_event(LogEvent.INTAKE, actor_id=ctx.staff.staff_id, encounter_id=st.encounter_id,
                  source_version_id=v.source_version_id, extraction_status=ext.status, sha256=sha)
        return views.source_view(src, v, ext), True

    # ------------------------------------------------------------------ check runs
    def run_checks(self, ctx: AuthContext, encounter_id: str, cutoff: datetime) -> CheckRunView:
        st = self._gate(ctx, encounter_id, A.RUN_CHECKS)
        with self._lock:
            now = utcnow()
            if cutoff > now or (st.runs and cutoff < st.runs[-1].cutoff):
                raise ApiError(ErrorCode.VALIDATION_FAILED)  # cutoffs only move forward, never into the future
            snapshot = st.snapshot()
            try:
                bundle = self._seam.load_bundle()
                result = self._seam.engine.run_checks(snapshot, bundle, cutoff, run_id=ids.new_id(), evaluated_at=now)
                self._seam.engine.answer_bubbles(snapshot, result, bundle, cutoff)  # derived views must be answerable
            except NotImplementedError:
                self._audit.record(AuditAction.CHECK_RUN, AuditTargetType.ENCOUNTER, AuditOutcome.ERROR,
                                   actor=ctx.staff, target_id=encounter_id)
                raise ApiError(ErrorCode.NOT_IMPLEMENTED) from None
            self._guard_engine_result(st, result)
            run_id = result.run.run_id
            raised, revised = [], []
            for f in result.flags:
                history = st.revisions.setdefault(f.flag_id, [])
                if not history or history[-1].revision != f.revision:
                    (revised if history else raised).append(f)
                    history.append(FlagRevision(revision=f.revision, evidence_revision=f.evidence_revision, state=f.state,
                                                owner_staff_id=f.owner_staff_id, evidence=f.evidence, run_id=run_id,
                                                decision_id=None, at=now))
            st.flags = {f.flag_id: f for f in result.flags}
            changes = views.change_views(result)
            st.runs.append(RunRecord(snapshot=snapshot, result=result, changes=changes, cutoff=cutoff,
                                     source_seq=st.source_seq))
        self._audit.record(AuditAction.CHECK_RUN, AuditTargetType.CHECK_RUN, AuditOutcome.SUCCESS, actor=ctx.staff,
                           target_id=run_id, hashes=(result.run.source_set_hash,))
        for f in raised:
            self._audit.record(AuditAction.FLAG_RAISED, AuditTargetType.FLAG, AuditOutcome.SUCCESS, actor=ctx.staff,
                               target_id=f.flag_id)
        for f in revised:
            self._audit.record(AuditAction.FLAG_REVISED, AuditTargetType.FLAG, AuditOutcome.SUCCESS, actor=ctx.staff,
                               target_id=f.flag_id)
        log_event(LogEvent.CHECK_RUN, actor_id=ctx.staff.staff_id, encounter_id=encounter_id, run_id=run_id,
                  ruleset_version=result.run.ruleset_version, registry_version=result.run.registry_version,
                  flags_raised=len(raised), count=len(result.flags),
                  sources_in_scope=self._verified_scope_count(snapshot, cutoff, result))
        return CheckRunView(run=result.run, flags=result.flags, changes=changes)

    @staticmethod
    def _verified_scope_count(snapshot: EncounterSnapshot, cutoff: datetime, result: CheckRunResult) -> int | None:
        """How many source versions the run read, for the log only. Scope rule (contracts): a Source is
        in scope iff source_time <= cutoff, and its latest version with version_time <= cutoff is read.
        The count is logged ONLY if these versions hash to the engine's own source_set_hash; otherwise
        None (dropped from the log), never an unverified number. (Was len(all sources): B3 #29.)"""
        shas = []
        for s in snapshot.sources:
            if s.source_time > cutoff:
                continue
            vs = [v for v in snapshot.versions if v.source_id == s.source_id and v.version_time <= cutoff]
            if vs:
                shas.append(max(vs, key=lambda v: v.version).sha256)
        return len(shas) if ids.source_set_hash(shas) == result.run.source_set_hash else None

    @staticmethod
    def _guard_engine_result(st: EncounterState, result: CheckRunResult) -> None:
        """Defence in depth for "no Tier 1 concern closes automatically": the engine may never move a
        flag into a human-only state, never drop a known flag, and only return this encounter's flags."""
        seen = {f.flag_id for f in result.flags}
        bad = any(fid not in seen for fid in st.flags)
        for f in result.flags:
            prior = st.flags.get(f.flag_id)
            if f.flag_id != ids.flag_id(f.rule_id.value, st.encounter_id, f.subject_key):
                bad = True
            if (prior is None or prior.state != f.state) and f.state in states.ENGINE_FORBIDDEN_TARGETS:
                bad = True
        if bad:
            raise ApiError(ErrorCode.INTERNAL_ERROR)

    def latest_run(self, ctx: AuthContext, encounter_id: str) -> CheckRunView:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        rec = self._latest(st)
        return CheckRunView(run=rec.result.run, flags=rec.result.flags, changes=rec.changes)  # as recorded

    @staticmethod
    def _latest(st: EncounterState) -> RunRecord:
        if not st.runs:
            raise ApiError(ErrorCode.NOT_FOUND)  # no check has run in this workspace yet
        return st.runs[-1]

    # ------------------------------------------------------------------ flags and decisions
    def list_flags(self, ctx: AuthContext, encounter_id: str) -> tuple[Flag, ...]:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        self._latest(st)
        return tuple(st.flags.values())

    def get_flag(self, ctx: AuthContext, encounter_id: str, flag_id: str) -> FlagDetail:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        if flag_id not in st.flags:
            raise ApiError(ErrorCode.NOT_FOUND)
        return self._flag_detail(st, flag_id)

    @staticmethod
    def _flag_detail(st: EncounterState, flag_id: str) -> FlagDetail:
        return FlagDetail(flag=st.flags[flag_id], revisions=tuple(st.revisions.get(flag_id, ())),
                          decisions=tuple(d for d in st.decisions if d.flag_id == flag_id))

    def decide(self, ctx: AuthContext, encounter_id: str, flag_id: str, req: DecisionRequest) -> FlagDetail:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        with self._lock:
            flag = st.flags.get(flag_id)
            if flag is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            now = utcnow()
            try:
                authz.check_decision(ctx.staff, st.facts, flag.tier, flag.owner_staff_id, req.action, now)
            except ApiError as exc:
                self._reject(ctx, flag, AuditOutcome.DENIED)
                raise ApiError(exc.code) from None
            if req.expected_revision != flag.revision:  # compare-and-swap (feedback 10): no lost decisions
                self._reject(ctx, flag, AuditOutcome.CONFLICT)
                raise ApiError(ErrorCode.STALE_REVISION, stale=self._stale(st, flag))
            try:
                to_state = states.decision_target(req.action, flag.state)
            except InvalidTransition:
                self._reject(ctx, flag, AuditOutcome.CONFLICT)
                raise ApiError(ErrorCode.INVALID_TRANSITION) from None
            code = self._decision_error(st, flag, req, now)
            if code is not None:
                self._reject(ctx, flag, AuditOutcome.INVALID)
                raise ApiError(code)
            changes_owner = req.action is D.REASSIGN or (req.action is D.EDIT and req.edit_field is EditField.OWNER)
            updates = dict(state=to_state, revision=flag.revision + 1)
            if req.action is D.MARK_READY_FOR_CLINICIAN:
                updates["ready_for_clinician"] = True
            if changes_owner:
                updates["owner_staff_id"] = req.new_owner_staff_id
            new = flag.model_copy(update=updates)
            decision = Decision(decision_id=ids.new_id(), flag_id=flag_id, encounter_id=encounter_id,
                                expected_revision=req.expected_revision, resulting_revision=new.revision,
                                action=req.action, actor_staff_id=ctx.staff.staff_id, actor_role=ctx.staff.role,
                                reason_code=req.reason_code, rationale_text=req.rationale_text,
                                new_owner_staff_id=req.new_owner_staff_id, edit_field=req.edit_field,
                                prepared_check=req.prepared_check, adjudicated_evidence=req.adjudicated_evidence,
                                from_state=flag.state, to_state=to_state, at=now)
            st.flags[flag_id] = new
            st.decisions.append(decision)
            st.revisions.setdefault(flag_id, []).append(FlagRevision(
                revision=new.revision, evidence_revision=new.evidence_revision, state=new.state,
                owner_staff_id=new.owner_staff_id, evidence=new.evidence, run_id=None,
                decision_id=decision.decision_id, at=now))
            st.feedback.append(self._feedback_event(new, decision, ctx.staff))
            detail = self._flag_detail(st, flag_id)
        self._audit.record(AuditAction.DECISION_RECORDED, AuditTargetType.FLAG, AuditOutcome.SUCCESS, actor=ctx.staff,
                           target_id=flag_id)
        log_event(LogEvent.DECISION, actor_id=ctx.staff.staff_id, role=ctx.staff.role, encounter_id=encounter_id,
                  flag_id=flag_id, rule_id=flag.rule_id, tier=flag.tier, state=to_state, decision_action=req.action,
                  reason_code=req.reason_code)
        return detail

    def _reject(self, ctx: AuthContext, flag: Flag, outcome: AuditOutcome) -> None:
        self._audit.record(AuditAction.DECISION_REJECTED, AuditTargetType.FLAG, outcome, actor=ctx.staff,
                           target_id=flag.flag_id)

    @staticmethod
    def _stale(st: EncounterState, flag: Flag) -> StaleRevision:
        last = next((d for d in reversed(st.decisions) if d.flag_id == flag.flag_id), None)
        return StaleRevision(current_revision=flag.revision, current_state=flag.state,
                             last_decision_action=last.action if last else None,
                             last_decision_actor_staff_id=last.actor_staff_id if last else None,
                             last_decision_at=last.at if last else None)

    def _valid_owner(self, st: EncounterState, staff_id: str | None, tier, now: datetime) -> bool:
        target = self._seed.staff.get(staff_id) if staff_id else None
        return (target is not None and authz.active_member(target, st.facts, now)
                and target.role in permissions.REASSIGN_TARGET_ROLES[int(tier)])

    def _decision_error(self, st: EncounterState, flag: Flag, req: DecisionRequest, now: datetime) -> ErrorCode | None:
        """Field rules per action (L15, 8.7). Fields that do not belong to the action are refused."""
        if req.action in states.REASON_REQUIRED:
            if req.reason_code is None:
                return ErrorCode.REASON_CODE_REQUIRED
            if req.reason_code not in permissions.REASONS_BY_ACTION[req.action]:
                return ErrorCode.REASON_CODE_NOT_ALLOWED
            if req.action is D.RESOLVE and req.reason_code not in permissions.RESOLVE_REASONS_BY_RULE.get(flag.rule_id, frozenset()):
                return ErrorCode.REASON_CODE_NOT_ALLOWED
        elif req.reason_code is not None:
            return ErrorCode.REASON_CODE_NOT_ALLOWED
        if req.action in states.RATIONALE_REQUIRED and not (req.rationale_text or "").strip():
            return ErrorCode.RATIONALE_REQUIRED
        if req.action is D.RESOLVE and req.reason_code in permissions.ADJUDICATION_REASONS:
            if not req.adjudicated_evidence:
                return ErrorCode.ADJUDICATION_REQUIRED
            cited = {(e.source_version_id, e.start, e.end) for e in flag.evidence}
            if any((r.source_version_id, r.start, r.end) not in cited for r in req.adjudicated_evidence):
                return ErrorCode.VALIDATION_FAILED
        elif req.adjudicated_evidence:
            return ErrorCode.VALIDATION_FAILED
        if (req.action is D.EDIT) != (req.edit_field is not None):
            return ErrorCode.VALIDATION_FAILED
        if req.action is D.REASSIGN or (req.action is D.EDIT and req.edit_field is EditField.OWNER):
            if req.new_owner_staff_id == flag.owner_staff_id or not self._valid_owner(st, req.new_owner_staff_id, flag.tier, now):
                return ErrorCode.REASSIGN_TARGET_INVALID
        elif req.new_owner_staff_id is not None:
            return ErrorCode.VALIDATION_FAILED
        if (req.action is D.MARK_READY_FOR_CLINICIAN) != (req.prepared_check is not None):
            return ErrorCode.VALIDATION_FAILED
        duplicate = req.action is D.DISMISS and req.reason_code is ReasonCode.DUPLICATE_OF
        if duplicate and (req.duplicate_of_flag_id is None or req.duplicate_of_flag_id == flag.flag_id
                          or req.duplicate_of_flag_id not in st.flags):
            return ErrorCode.VALIDATION_FAILED
        if not duplicate and req.duplicate_of_flag_id is not None:
            return ErrorCode.VALIDATION_FAILED
        return None

    # ------------------------------------------------------------------ derived views
    def _derived(self, st: EncounterState) -> tuple[RunRecord, EncounterSnapshot, CheckRunResult, tuple[QuestionBubble, ...]]:
        """Bubbles/summary are recomputed by the engine from CURRENT flag states and decisions, so a
        view never shows a pre-decision state as current. With the stub engine any read after a
        decision is 501 not_implemented (explicit), never a stale golden."""
        rec = self._latest(st)
        snap = rec.snapshot.model_copy(update=dict(decisions=tuple(st.decisions)))
        result = rec.result.model_copy(update=dict(flags=tuple(st.flags.values())))
        try:
            bubbles = self._seam.engine.answer_bubbles(snap, result, self._seam.load_bundle(), rec.cutoff)
        except NotImplementedError:
            raise ApiError(ErrorCode.NOT_IMPLEMENTED) from None
        return rec, snap, result, bubbles

    def bubbles(self, ctx: AuthContext, encounter_id: str) -> BubbleList:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        with self._lock:
            rec, _, _, bubbles = self._derived(st)
        return BubbleList(cutoff=rec.cutoff, bubbles=bubbles, ai_status=AIDraftStatus.DISABLED)

    def summary(self, ctx: AuthContext, encounter_id: str) -> Summary:
        st = self._gate(ctx, encounter_id, A.VIEW_SUMMARY)
        with self._lock:
            rec, snap, result, bubbles = self._derived(st)
            try:
                out = self._seam.engine.build_summary(snap, result, bubbles, tuple(st.decisions), self._seam.load_bundle(),
                                                      rec.cutoff, generated_at=utcnow())
            except NotImplementedError:
                raise ApiError(ErrorCode.NOT_IMPLEMENTED) from None
            if st.source_seq != rec.source_seq:
                out = out.model_copy(update=dict(stale_after_source_change=True))
        self._audit.record(AuditAction.SUMMARY_GENERATED, AuditTargetType.SUMMARY, AuditOutcome.SUCCESS, actor=ctx.staff,
                           target_id=encounter_id)
        return out

    def closure(self, ctx: AuthContext, encounter_id: str) -> ClosureView:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        with self._lock:
            rec = self._latest(st)
            return views.closure_view(encounter_id, rec.cutoff, st.flags.values(), st.decisions)

    def glance(self, ctx: AuthContext, encounter_id: str) -> GlanceView:
        st = self._gate(ctx, encounter_id, A.READ_ENCOUNTER)
        with self._lock:
            rec, _, _, bubbles = self._derived(st)
            closure = views.closure_view(encounter_id, rec.cutoff, st.flags.values(), st.decisions)
            return views.glance_view(closure, st.flags.values(), bubbles)

    def attempt_close(self, ctx: AuthContext, encounter_id: str) -> ClosureView:
        """Responsible clinician only. Blocked while any Tier 1 blocks (states.blocks_closure), while no
        check has run, if sources changed since the last run, or if the run's cutoff does not cover
        every source version in the workspace (closure must never rest on unchecked text)."""
        st = self._gate(ctx, encounter_id, A.CLOSE_ENCOUNTER)
        with self._lock:
            rec = st.runs[-1] if st.runs else None
            view = views.closure_view(encounter_id, rec.cutoff, st.flags.values(), st.decisions) if rec else None
            covered = rec is not None and rec.source_seq == st.source_seq and all(
                st.sources[v.source_id].source_time <= rec.cutoff and v.version_time <= rec.cutoff for v in st.versions)
            blocked = view is None or not covered or view.status is ClosureStatus.BLOCKED
        self._audit.record(AuditAction.CLOSURE_ATTEMPTED, AuditTargetType.ENCOUNTER,
                           AuditOutcome.DENIED if blocked else AuditOutcome.SUCCESS, actor=ctx.staff, target_id=encounter_id)
        if blocked:
            raise ApiError(ErrorCode.CLOSURE_BLOCKED)
        return view  # type: ignore[return-value]

    # ------------------------------------------------------------------ documents
    def issue_document_token(self, ctx: AuthContext, encounter_id: str, version_id: str) -> DocumentTokenView:
        st = self._gate(ctx, encounter_id, A.VIEW_DOCUMENT)
        if version_id not in st.blobs:
            raise ApiError(ErrorCode.NOT_FOUND)  # only original PDFs are served as documents
        token = secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(seconds=self._settings.document_token_ttl_s)
        with self._lock:
            self._doc_tokens[_h(token)] = _DocToken(ctx.staff.staff_id, ctx.workspace_hash, encounter_id, version_id, expires)
        self._audit.record(AuditAction.DOCUMENT_TOKEN_ISSUED, AuditTargetType.DOCUMENT, AuditOutcome.SUCCESS,
                           actor=ctx.staff, target_id=version_id)
        return DocumentTokenView(document_token=token, expires_at=expires, single_use=True)

    def read_document(self, staff: Staff, token: str) -> bytes:
        """Single use: the token is consumed on first presentation, by anyone. Bound to the issuing
        staff member and workspace; care-team scope is re-checked at read time."""
        with self._lock:
            dt = self._doc_tokens.pop(_h(token), None)
        if dt is None or dt.expires_at <= utcnow() or dt.staff_id != staff.staff_id:
            self._audit.record(AuditAction.DOCUMENT_READ, AuditTargetType.DOCUMENT, AuditOutcome.DENIED, actor=staff)
            raise ApiError(ErrorCode.DOCUMENT_TOKEN_INVALID)
        ws = self._workspaces.get(dt.workspace_hash)
        if ws is None:
            raise ApiError(ErrorCode.DOCUMENT_TOKEN_INVALID)
        st = self._gate(AuthContext(staff, ws.workspace_id, dt.workspace_hash), dt.encounter_id, A.VIEW_DOCUMENT)
        data = st.blobs.get(dt.version_id)
        if data is None:
            raise ApiError(ErrorCode.DOCUMENT_TOKEN_INVALID)
        self._audit.record(AuditAction.DOCUMENT_READ, AuditTargetType.DOCUMENT, AuditOutcome.SUCCESS, actor=staff,
                           target_id=dt.version_id)
        return data

    # ------------------------------------------------------------------ feedback (B4 consumes)
    @staticmethod
    def _feedback_event(flag: Flag, decision: Decision, actor: Staff, *, usefulness=None, time_on_screen_ms=None,
                        corrected_owner=None) -> FeedbackEvent:
        rule_version = _RULE_VERSION.search(flag.check_version + ";")
        ruleset = _RULESET_VERSION.search(flag.check_version)
        return FeedbackEvent(feedback_id=ids.new_id(), flag_id=flag.flag_id, rule_id=flag.rule_id,
                             rule_version=int(rule_version.group(1)) if rule_version else 1,
                             ruleset_version=ruleset.group(1) if ruleset else "unknown", action=decision.action,
                             reason_code=decision.reason_code,
                             corrected_owner_staff_id=corrected_owner or decision.new_owner_staff_id,
                             usefulness=usefulness, time_on_screen_ms=time_on_screen_ms, actor_role=actor.role,
                             at=utcnow())

    def record_feedback(self, ctx: AuthContext, encounter_id: str, req: FeedbackRequest) -> FeedbackEvent:
        """Usefulness feedback attaches to the flag's latest human decision (FeedbackEvent.action is
        required); feedback on a flag nobody has decided yet is refused with 409 invalid_transition."""
        st = self._gate(ctx, encounter_id, A.RECORD_FEEDBACK)
        with self._lock:
            flag = st.flags.get(req.flag_id)
            if flag is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            last = next((d for d in reversed(st.decisions) if d.flag_id == flag.flag_id), None)
            if last is None:
                raise ApiError(ErrorCode.INVALID_TRANSITION)
            corrected = req.corrected_owner_staff_id
            if corrected is not None:
                target = self._seed.staff.get(corrected)
                if target is None or not authz.active_member(target, st.facts, utcnow()):
                    raise ApiError(ErrorCode.REASSIGN_TARGET_INVALID)
            ev = self._feedback_event(flag, last, ctx.staff, usefulness=req.usefulness,
                                      time_on_screen_ms=req.time_on_screen_ms, corrected_owner=corrected)
            st.feedback.append(ev)
            return ev

    def feedback_events(self, ctx: AuthContext, encounter_id: str) -> tuple[FeedbackEvent, ...]:
        st = self._gate(ctx, encounter_id, A.RECORD_FEEDBACK)
        return tuple(st.feedback)

    # ------------------------------------------------------------------ aggregate seam (B4 consumes)
    def aggregate_rows(self, staff: Staff) -> tuple[AggregateRow, ...]:
        """Content-free, identifier-free rows for B4's aggregate view; aggregate roles only.

        Store-layer check (the route layer is ``authz.require_aggregate_viewer``). Covers every live
        workspace in this process. In the demonstrator each workspace is one user's copy of the same
        synthetic case, so rows count workspace copies, not distinct real encounters. Counting,
        age buckets and small-cell suppression ("<5") are B4's."""
        if not permissions.is_allowed(A.VIEW_AGGREGATE, staff.role, frozenset()):
            self._audit.record(AuditAction.AGGREGATE_READ, AuditTargetType.AGGREGATE, AuditOutcome.DENIED, actor=staff)
            raise ApiError(ErrorCode.FORBIDDEN_ROLE)
        now = utcnow()
        rows: list[AggregateRow] = []
        with self._lock:
            for ws in self._workspaces.values():
                if ws.expires_at <= now:
                    continue
                for st in ws.encounters.values():
                    for f in st.flags.values():
                        decs = [d for d in st.decisions if d.flag_id == f.flag_id]
                        owner = self._seed.staff.get(f.owner_staff_id)
                        rows.append(AggregateRow(rule_id=f.rule_id, tier=f.tier, state=f.state, created_at=f.created_at,
                                                 owner_role=owner.role if owner else None,
                                                 first_decision_at=decs[0].at if decs else None,
                                                 disposition=decs[-1].action if decs else None))
        self._audit.record(AuditAction.AGGREGATE_READ, AuditTargetType.AGGREGATE, AuditOutcome.SUCCESS, actor=staff)
        return tuple(rows)
