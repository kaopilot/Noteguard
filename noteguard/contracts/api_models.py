"""Request/response models for the API (frozen, B0). Entities come from types.py;
these are the view shapes the routes return. B3 builds against these via docs/openapi.json."""

from __future__ import annotations

from pydantic import Field, NonNegativeInt, PositiveInt

from .types import (
    AIDraftStatus,
    BubbleStatus,
    CareTeamMembership,
    ChangeKind,
    CheckRun,
    ClosureStatus,
    Decision,
    Discipline,
    Encounter,
    Evidence,
    ExtractionStatus,
    Flag,
    FlagState,
    Frozen,
    OpaqueId,
    PageSpan,
    QuestionBubble,
    Role,
    RuleId,
    SourceType,
    Staff,
    SubjectKey,
    Tier,
    UtcDatetime,
    Usefulness,
)


class ErrorBody(Frozen):
    error_code: str


class LoginRequest(Frozen):
    """Synthetic login for the demonstrator: pick a synthetic staff member."""

    staff_id: OpaqueId


class EncounterListItem(Frozen):
    encounter_id: OpaqueId
    encounter_ref: str
    patient_label: str
    setting: str
    responsible_clinician_id: OpaqueId | None


class SourceView(Frozen):
    """Metadata only (no text). Text is fetched per version via SOURCE_TEXT."""

    source_id: OpaqueId
    source_version_id: OpaqueId = Field(alias="note_version_id")
    version: PositiveInt
    supersedes_version_id: OpaqueId | None
    title: str
    source_type: SourceType
    discipline: Discipline
    author_staff_id: OpaqueId
    source_time: UtcDatetime
    version_time: UtcDatetime
    received_at: UtcDatetime
    sha256: str
    extraction_status: ExtractionStatus
    extraction_note: str | None = None
    page_count: NonNegativeInt = 0


class EncounterView(Frozen):
    encounter: Encounter
    patient_label: str
    staff: tuple[Staff, ...]
    memberships: tuple[CareTeamMembership, ...]
    sources: tuple[SourceView, ...]  # every version, ordered (source_time, received_at, id)


class SourceText(Frozen):
    source_version_id: OpaqueId = Field(alias="note_version_id")
    extraction_status: ExtractionStatus
    text: str  # clinical content: POST/GET body only, never URL, never logged
    pages: tuple[PageSpan, ...] = ()


class AddTextSourceRequest(Frozen):
    title: str = Field(max_length=200)
    discipline: Discipline
    author_staff_id: OpaqueId
    source_time: UtcDatetime
    text: str = Field(min_length=1, max_length=200_000)
    source_id: OpaqueId | None = None  # set to add a NEW VERSION of an existing source
    identifier_namespace: str = "noteguard-paste"
    external_id: str | None = None
    idempotency_key: str | None = None


class AddPdfSourceForm(Frozen):
    """multipart/form-data fields of POST SOURCES_PDF (the file part is named "file").
    Declared here so the form shape is frozen; B2 maps it with fastapi.Form/File."""

    title: str = Field(max_length=200)
    discipline: Discipline
    author_staff_id: OpaqueId  # uploader = accountable owner of the external document
    source_time: UtcDatetime
    source_id: OpaqueId | None = None  # set to add a NEW VERSION of an existing source
    identifier_namespace: str = "noteguard-upload"
    external_id: str | None = None
    idempotency_key: str | None = None


PDF_FILE_FIELD = "file"


class CheckRunRequest(Frozen):
    cutoff: UtcDatetime


class ChangeView(Frozen):
    """Diff chip data: '+ new', '~ explicit change', '= carried forward', '! contradicts'."""

    kind: ChangeKind
    subject_key: SubjectKey
    from_evidence: Evidence | None
    to_evidence: Evidence | None


class CheckRunView(Frozen):
    run: CheckRun
    flags: tuple[Flag, ...]
    changes: tuple[ChangeView, ...]


class FlagRevision(Frozen):
    revision: PositiveInt
    evidence_revision: PositiveInt
    state: FlagState
    owner_staff_id: OpaqueId
    evidence: tuple[Evidence, ...]
    run_id: OpaqueId | None  # set when the engine produced this revision
    decision_id: OpaqueId | None  # set when a human decision produced it
    at: UtcDatetime


class FlagDetail(Frozen):
    flag: Flag
    revisions: tuple[FlagRevision, ...]
    decisions: tuple[Decision, ...]


class BubbleList(Frozen):
    cutoff: UtcDatetime
    bubbles: tuple[QuestionBubble, ...]  # ordered by rank, then subject_key
    ai_status: AIDraftStatus = AIDraftStatus.DISABLED


class DocumentTokenView(Frozen):
    document_token: str
    expires_at: UtcDatetime
    single_use: bool = True


class FeedbackRequest(Frozen):
    flag_id: str
    usefulness: Usefulness
    time_on_screen_ms: NonNegativeInt | None = None
    corrected_owner_staff_id: OpaqueId | None = None


class AggregateCell(Frozen):
    """PHI-minimised: no content, no patient or encounter identifiers; small cells '<5'."""

    rule_id: RuleId
    tier: Tier
    state: FlagState
    age_bucket: str  # e.g. "<4h", "4-24h", ">24h"
    count: str  # integer as string, or "<5"
    # CCR-04 (approved): time from created_at to the first human decision, "<1h" | "1-4h" | ">4h",
    # or "none_yet" when no decision exists. Part of the cell key, so "<5" still applies.
    response_time_bucket: str | None = None


class AggregateView(Frozen):
    generated_at: UtcDatetime
    ruleset_version: str
    cells: tuple[AggregateCell, ...]
    small_cell_threshold: PositiveInt = 5


class AIStatusView(Frozen):
    status: AIDraftStatus
    detail: str  # e.g. "AI drafting disabled"


class GlanceView(Frozen):
    """Top strip (Section 13): computed server-side; the UI only renders it."""

    encounter_id: OpaqueId
    cutoff: UtcDatetime
    closure_status: ClosureStatus
    open_tier1: NonNegativeInt
    open_tier2: NonNegativeInt
    open_tier3: NonNegativeInt
    tier1_owner_ids: tuple[OpaqueId, ...]
    top_bubble_ids: tuple[str, ...]
    top_bubble_statuses: tuple[BubbleStatus, ...]


class SessionView(Frozen):
    staff_id: OpaqueId
    display_name: str
    role: Role
    discipline: Discipline
