"""Frozen domain contract for Noteguard (B0).

Every enum and every entity from Section 7 of the build context is defined here
and ONLY here. Other modules import from this file; the seam test
(tests/test_contract_seams.py) fails if any module outside ``noteguard/contracts``
defines its own Enum, role list, reason-code list, term list or log key list.

Conventions (Section 18.3):
- Offsets are Unicode code points into the ORIGINAL extracted text, end exclusive.
  PDFs use document-global offsets into the concatenated extraction; evidence also
  carries ``page``.
- Times are timezone-aware UTC. Display is Asia/Singapore (UI concern).
- IDs are opaque UUIDv4 strings, except ``flag_id`` / ``bubble_id`` which are
  stable hashes computed by ``noteguard.contracts.ids`` only.
- Wire names: evidence serialises ``source_version_id`` as ``note_version_id``
  (appendix JSON shape). All models serialise by alias.

Changing anything here after CP0 requires a contract change request
(docs/contract_changes/CCR-NN.md).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    model_validator,
)

CONTRACT_VERSION = "b0-1"


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class Frozen(BaseModel):
    """Immutable, strict-shape base for every contract entity."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
        use_enum_values=False,
    )


# ---------------------------------------------------------------------------
# Enums (ALL of them; nothing outside contracts/ may define its own)
# ---------------------------------------------------------------------------


class Tier(IntEnum):
    T1 = 1  # potential immediate safety or major closure risk
    T2 = 2  # material continuity or follow-up gap
    T3 = 3  # documentation-quality concern


class Lens(str, Enum):
    CONSISTENCY = "consistency"
    CONTINUITY = "continuity"
    COMPLETENESS = "completeness"
    CONTRADICTION = "contradiction"
    CLOSURE = "closure"


class FlagState(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    EDITED = "edited"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class RuleId(str, Enum):
    """Rule catalog (Section 8.2). MVP rules are enabled in rulesets/v1.json;
    stretch rules exist here so their wire values are frozen, and are disabled
    in v1 until a CCR adds golden expectations for them."""

    CRIT_001 = "CRIT-001"  # critical observation unacknowledged (T1)
    ALG_001 = "ALG-001"  # allergy conflict (T1)
    DOSE_001 = "DOSE-001"  # dose discrepancy (T2)
    DOSE_002 = "DOSE-002"  # unparsed dose (T3)
    PEND_001 = "PEND-001"  # pending action without owner and timing (T2)
    PDF_001 = "PDF-001"  # incomplete extraction (T2)
    DIFF_001 = "DIFF-001"  # possible copied-forward text (T3)
    OWN_001 = "OWN-001"  # no responsible clinician recorded (T1; Section 8.6)
    DET_001 = "DET-001"  # stretch: reassurance after deterioration (T1)
    LAT_001 = "LAT-001"  # stretch: laterality conflict (T1)
    META_001 = "META-001"  # stretch: incomplete metadata (T3)
    NEXT_001 = "NEXT-001"  # stretch: no next step (T3)


class FlagCategory(str, Enum):
    """Wire ``category`` values (kebab-case, as in the appendix example)."""

    CRITICAL_OBSERVATION_UNACKNOWLEDGED = "critical-observation-unacknowledged"
    ALLERGY_CONFLICT = "allergy-conflict"
    DOSE_DISCREPANCY = "dose-discrepancy"
    UNPARSED_DOSE = "unparsed-dose"
    PENDING_ACTION_OWNER_TIMING = "pending-action-owner-timing"
    INCOMPLETE_EXTRACTION = "incomplete-extraction"
    POSSIBLE_COPIED_FORWARD_TEXT = "possible-copied-forward-text"
    NO_RESPONSIBLE_CLINICIAN = "no-responsible-clinician"
    REASSURANCE_AFTER_DETERIORATION = "reassurance-after-deterioration"
    LATERALITY_CONFLICT = "laterality-conflict"
    INCOMPLETE_METADATA = "incomplete-metadata"
    NO_NEXT_STEP = "no-next-step"


class OwnerRouting(str, Enum):
    """Default owner routing (Section 8.6)."""

    SOURCE_NOTE_OWNER = "source_note_owner"
    RESPONSIBLE_CLINICIAN = "responsible_clinician"
    RESPONSIBLE_CLINICIAN_PLUS_PHARMACY = "responsible_clinician_plus_pharmacy"
    SINGLE_SOURCE_OWNER_ELSE_RESPONSIBLE = "single_source_owner_else_responsible"


class Discipline(str, Enum):
    CLINICIAN = "clinician"
    NURSING = "nursing"
    PHYSIOTHERAPY = "physiotherapy"
    COUNSELLING_SOCIAL_WORK = "counselling_social_work"
    PHARMACY = "pharmacy"
    OTHER = "other"


class Role(str, Enum):
    """System (authorisation) role of a staff member. Distinct from Discipline,
    which describes a source document, and from TeamRole."""

    CLINICIAN = "clinician"
    NURSE = "nurse"
    PHARMACIST = "pharmacist"
    ALLIED_HEALTH = "allied_health"  # physiotherapy, counselling/social work
    CLERICAL_STAFF = "clerical_staff"  # "staff prepare"
    CLINIC_ADMIN = "clinic_admin"  # not a clinical superuser
    MEDICAL_DIRECTOR = "medical_director"  # aggregate view only
    QUALITY_RISK = "quality_risk"  # aggregate view only
    LEGAL = "legal"  # aggregate view only


class TeamRole(str, Enum):
    RESPONSIBLE_CLINICIAN = "responsible_clinician"
    ATTENDING = "attending"
    MEMBER = "member"


class Relation(str, Enum):
    """Relationship of an actor to an encounter/flag, derived server-side."""

    CARE_TEAM_MEMBER = "care_team_member"
    RESPONSIBLE_CLINICIAN = "responsible_clinician"
    FLAG_OWNER = "flag_owner"


class SourceType(str, Enum):
    PASTED_TEXT = "pasted_text"
    PDF = "pdf"
    FHIR_DOCUMENTREFERENCE = "fhir_documentreference"
    HL7V2 = "hl7v2"
    CDA = "cda"
    TRANSCRIPT_SEGMENT = "transcript_segment"  # audio-ready; not built


class ExtractionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_TEXT_LAYER = "no_text_layer"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"  # pasted text: the text IS the source


#: Extraction statuses over which an absence answer may be given (Section 8.8).
ABSENCE_SAFE_EXTRACTION = frozenset({ExtractionStatus.COMPLETE, ExtractionStatus.NOT_APPLICABLE})


class FactType(str, Enum):
    ALLERGY = "allergy"
    MEDICATION = "medication"
    OBSERVATION = "observation"  # lab result or vital sign
    RESPONSE = "response"  # review / repeat / treatment / escalation / transfer
    PENDING_ACTION = "pending_action"
    CLINICAL_STATUS = "clinical_status"  # "patient stable", "fit for discharge"
    UNPARSED_DOSE = "unparsed_dose"  # number + dose unit not attached to a regimen
    PROCEDURE_SITE = "procedure_site"  # laterality (stretch)
    NEXT_STEP = "next_step"


class ResponseKind(str, Enum):
    REVIEW = "review"
    REPEAT = "repeat"
    TREATMENT = "treatment"
    ESCALATION = "escalation"
    TRANSFER = "transfer"


class Polarity(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class Certainty(IntEnum):
    """Ordinal certainty of an assertion, adapted from REVIEW_STANDARD_OBSERVATIONS
    §4.1. Higher = more certain. Uncertain wording never becomes a negative."""

    UNKNOWN = 0
    QUERIED = 1  # "?penicillin", "query allergy"
    POSSIBLE = 2
    LIKELY = 3
    ASSERTED = 4  # plain statement


class AssertionScope(str, Enum):
    """Scope of an assertion (care-core NormalizedFact.assertion_scope, refined)."""

    SPECIFIC = "specific"  # one named substance / drug / analyte
    CLASS = "class"  # a drug or allergen class
    ALL_DRUGS = "all_drugs"  # NKDA, "no known drug allergies"
    ALL_ALLERGIES = "all_allergies"  # "no known allergies"


class ChangeKind(str, Enum):
    NEW = "new"
    EXPLICIT_CHANGE = "explicit_change"
    REWORDED = "reworded"
    CARRIED_FORWARD = "carried_forward"
    REMOVED = "removed"


class EvidenceRole(str, Enum):
    CLAIM = "claim"  # the assertion the flag is about (earlier side of a conflict)
    COUNTER_CLAIM = "counter_claim"  # the later / other side of a conflict
    ORIGIN = "origin"  # where carried-forward text first appeared
    SUPPRESSOR = "suppressor"  # a documented response that suppresses/supersedes
    TRIGGER = "trigger"  # the assertion that triggered a question bubble
    EXTRACTION_GAP = "extraction_gap"  # page with no/partial text (start == end)
    MISSING_RESPONSE_WINDOW = "missing_response_window"  # reserved; unused in v1 goldens
    ENCOUNTER_RECORD = "encounter_record"  # grounded in a structured encounter field, not a note (OWN-001)


class RecordField(str, Enum):
    """Structured encounter fields an ``encounter_record`` evidence item may name."""

    ENCOUNTER_RESPONSIBLE_CLINICIAN = "encounter.responsible_clinician_id"


class DecisionAction(str, Enum):
    ACCEPT = "accept"
    EDIT = "edit"
    REASSIGN = "reassign"
    MARK_READY_FOR_CLINICIAN = "mark_ready_for_clinician"
    DISMISS = "dismiss"
    RESOLVE = "resolve"


class EngineTransition(str, Enum):
    """State changes the engine (never a human) may make. See states.py."""

    RAISE = "raise"
    SUPERSEDE = "supersede"
    REOPEN = "reopen"


class PermissionAction(str, Enum):
    READ_ENCOUNTER = "read_encounter"
    ADD_SOURCE = "add_source"
    RUN_CHECKS = "run_checks"
    VIEW_SUMMARY = "view_summary"
    VIEW_DOCUMENT = "view_document"
    RECORD_FEEDBACK = "record_feedback"
    CLOSE_ENCOUNTER = "close_encounter"
    VIEW_AGGREGATE = "view_aggregate"
    RESET_WORKSPACE = "reset_workspace"
    DECIDE_ACCEPT = "decide_accept"
    DECIDE_EDIT = "decide_edit"
    DECIDE_REASSIGN = "decide_reassign"
    DECIDE_MARK_READY = "decide_mark_ready_for_clinician"
    DECIDE_DISMISS = "decide_dismiss"
    DECIDE_RESOLVE = "decide_resolve"


class ReasonCode(str, Enum):
    """Fixed reason codes (L15). Which codes each action allows is in permissions.py."""

    # dismiss
    EXTRACTION_ERROR = "extraction_error"
    ALREADY_ADDRESSED_IN_SOURCE = "already_addressed_in_source"
    WRONG_ENCOUNTER = "wrong_encounter"
    DUPLICATE_OF = "duplicate_of"
    NOT_CLINICALLY_RELEVANT = "not_clinically_relevant"
    # resolve
    RESPONSE_DOCUMENTED_CONFIRMED = "response_documented_confirmed"  # confirm a superseded flag
    ALLERGY_ENTRY_CONFIRMED = "allergy_entry_confirmed"  # adjudication
    INTOLERANCE_NOT_ALLERGY = "intolerance_not_allergy"  # adjudication
    DOSE_ENTRY_CURRENT = "dose_entry_current"  # adjudication
    OWNER_AND_TIMING_DOCUMENTED = "owner_and_timing_documented"
    MANUAL_REVIEW_COMPLETED = "manual_review_completed"
    OCR_COMPLETED = "ocr_completed"
    STATEMENT_CONFIRMED_CURRENT = "statement_confirmed_current"
    STATEMENT_CORRECTED_IN_SOURCE = "statement_corrected_in_source"
    WORK_COMPLETED_DOCUMENTED = "work_completed_documented"


class PreparedCheck(str, Enum):
    """What a non-clinician attaches when marking a flag ready for clinician (L16)."""

    PHARMACY_CHECK_ATTACHED = "pharmacy_check_attached"
    PATIENT_VERIFIED = "patient_verified"
    SOURCE_DOCUMENT_CHECKED = "source_document_checked"
    MANUAL_PDF_REVIEW_DONE = "manual_pdf_review_done"


class EditField(str, Enum):
    OWNER = "owner"
    EXPLANATION = "explanation"
    RESOLUTION = "resolution"


class BubbleStatus(str, Enum):
    """The ONLY answers a question bubble may give (Section 8.8)."""

    DOCUMENTED = "documented"
    NOT_DOCUMENTED_IN_SUPPLIED_SOURCES = "not_documented_in_supplied_sources"
    CONFLICTING = "conflicting"
    INCOMPLETE_EXTRACTION = "incomplete_extraction"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class BubbleTriggerKind(str, Enum):
    FLAG_RULE = "flag_rule"  # one bubble per current flag of a rule
    CRITICAL_OBSERVATION = "critical_observation"  # one bubble per critical analyte in scope


class BubbleAnswerMode(str, Enum):
    """How a template is answered. Fixes which statuses a template can return."""

    CONFLICT_STATE = "conflict_state"  # conflicting while the flag is unresolved
    ABSENCE_SEARCH = "absence_search"  # documented | not_documented | incomplete_extraction
    HUMAN_REVIEW = "human_review"  # requires_human_review


class CheckRunOutcome(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_EXTRACTION_GAPS = "completed_with_extraction_gaps"
    FAILED = "failed"


class ClosureStatus(str, Enum):
    BLOCKED = "blocked"  # at least one Tier 1 blocks closure
    CLEAR_WITH_OPEN_TIER2 = "clear_with_open_tier2"
    CLEAR = "clear"


class SummaryClaimTemplate(str, Enum):
    OPEN_PRIORITY = "open_priority"  # an unresolved Tier 1/2 flag with owner
    DECISION_RECORD = "decision_record"  # a human decision with owner, reason, time
    TOP_QUESTION = "top_question"  # one of the top three non-documented bubbles


class AuditAction(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    WORKSPACE_CREATE = "workspace_create"
    WORKSPACE_RESET = "workspace_reset"
    ENCOUNTER_READ = "encounter_read"
    SOURCE_VERSION_ADDED = "source_version_added"
    CHECK_RUN = "check_run"
    FLAG_RAISED = "flag_raised"
    FLAG_REVISED = "flag_revised"
    DECISION_RECORDED = "decision_recorded"
    DECISION_REJECTED = "decision_rejected"
    CLOSURE_ATTEMPTED = "closure_attempted"
    SUMMARY_GENERATED = "summary_generated"
    DOCUMENT_TOKEN_ISSUED = "document_token_issued"
    DOCUMENT_READ = "document_read"
    AGGREGATE_READ = "aggregate_read"
    AI_DRAFT_REQUESTED = "ai_draft_requested"
    ACCESS_DENIED = "access_denied"


class AuditTargetType(str, Enum):
    WORKSPACE = "workspace"
    ENCOUNTER = "encounter"
    SOURCE_VERSION = "source_version"
    CHECK_RUN = "check_run"
    FLAG = "flag"
    DECISION = "decision"
    SUMMARY = "summary"
    DOCUMENT = "document"
    AGGREGATE = "aggregate"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID = "invalid"
    ERROR = "error"


class Usefulness(str, Enum):
    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    WRONG_OWNER = "wrong_owner"
    STALE_WORDING = "stale_wording"
    MISSING_RULE = "missing_rule"


class AIDraftStatus(str, Enum):
    DISABLED = "disabled"  # default; UI says "AI drafting disabled" (L10)
    UNAVAILABLE_FALLBACK = "unavailable_fallback"  # timeout/5xx -> rule text shown
    REJECTED_FALLBACK = "rejected_fallback"  # validator discarded output -> rule text
    VALIDATED = "validated"


class ConsentStatus(str, Enum):
    NOT_RECORDED = "not_recorded"
    GRANTED = "granted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class ThresholdStatus(str, Enum):
    PLACEHOLDER_PENDING_CLINICAL_GOVERNANCE = "placeholder_pending_clinical_governance"
    APPROVED = "approved"


class TermKind(str, Enum):
    DRUG = "drug"
    DRUG_CLASS = "drug_class"
    ALLERGEN = "allergen"
    ANALYTE = "analyte"
    TEST = "test"  # tests, results, referrals that can be pending
    STATUS = "status"  # reassuring / discharge-readiness statements
    SITE = "site"


class CueKind(str, Enum):
    NEGATION = "negation"
    UNCERTAINTY = "uncertainty"
    CHANGE = "change"  # increased to, reduced to, changed to, stopped, held
    PENDING = "pending"  # pending, awaiting, sent, to chase
    RESPONSE_REVIEW = "response_review"
    RESPONSE_REPEAT = "response_repeat"
    RESPONSE_TREATMENT = "response_treatment"
    RESPONSE_ESCALATION = "response_escalation"
    RESPONSE_TRANSFER = "response_transfer"
    TIMING = "timing"  # regex-like cue strings for explicit timing
    OWNER = "owner"  # role nouns that count as an explicit owner
    ALLERGY_KEYWORD = "allergy_keyword"


class RulesetStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class ProposalKind(str, Enum):
    ADD_SYNONYM = "add_synonym"
    ADJUST_TIER3_THRESHOLD = "adjust_tier3_threshold"
    RETIRE_TIER3_RULE = "retire_tier3_rule"
    ADD_QUESTION_TEMPLATE = "add_question_template"
    LOWER_TIER = "lower_tier"  # always refused for protected rules
    DISABLE_RULE = "disable_rule"  # always refused for protected rules
    NARROW_RULE = "narrow_rule"  # always refused for protected rules


# ---------------------------------------------------------------------------
# Small value types
# ---------------------------------------------------------------------------

OpaqueId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FlagIdStr = Annotated[str, Field(pattern=r"^flg_[0-9a-f]{24}$")]
BubbleIdStr = Annotated[str, Field(pattern=r"^bbl_[0-9a-f]{24}$")]
SubjectKey = Annotated[str, Field(min_length=1, max_length=200)]
CheckVersionStr = Annotated[
    str, Field(pattern=r"^ruleset@[A-Za-z0-9.\-]+;rule@[A-Z]+-\d{3}\.\d+;registry@[A-Za-z0-9.\-]+$")
]
UtcDatetime = AwareDatetime


# ---------------------------------------------------------------------------
# People, encounter, care team
# ---------------------------------------------------------------------------


class Clinic(Frozen):
    clinic_id: OpaqueId
    display_name: str


class Patient(Frozen):
    patient_id: OpaqueId
    patient_ref: OpaqueId  # opaque; never MRN/NRIC
    display_label: str  # synthetic label only, e.g. "Synthetic patient A1"


class Encounter(Frozen):
    encounter_id: OpaqueId
    encounter_ref: str  # display reference, e.g. "ENC-A1"
    clinic_id: OpaqueId
    patient_id: OpaqueId
    setting: str  # e.g. "medical ward"
    started_at: UtcDatetime
    responsible_clinician_id: OpaqueId | None
    attending_clinician_id: OpaqueId


class Staff(Frozen):
    staff_id: OpaqueId
    display_name: str  # synthetic
    discipline: Discipline
    role: Role
    clinic_id: OpaqueId


class CareTeamMembership(Frozen):
    encounter_id: OpaqueId
    staff_id: OpaqueId
    team_role: TeamRole
    valid_from: UtcDatetime
    valid_to: UtcDatetime | None = None


# ---------------------------------------------------------------------------
# Sources, versions, extraction
# ---------------------------------------------------------------------------


class Source(Frozen):
    """Logical document. Content lives in SourceVersion + TextExtraction."""

    source_id: OpaqueId
    encounter_id: OpaqueId
    source_system: str  # e.g. "noteguard-paste", "fixture-emr"
    identifier_namespace: str
    external_id: str
    source_type: SourceType
    author_staff_id: OpaqueId  # accountable owner (uploader for external documents)
    discipline: Discipline  # discipline of the document, not necessarily of the uploader
    title: str
    source_time: UtcDatetime  # clinical time of the document


class SourceVersion(Frozen):
    """IMMUTABLE. New content = a new row with supersedes_version_id set."""

    source_version_id: OpaqueId
    source_id: OpaqueId
    version: PositiveInt  # EMR version or ingest sequence
    version_time: UtcDatetime  # when this version was recorded; decides cutoff scope
    received_at: UtcDatetime
    sha256: Sha256Hex  # of the original bytes (UTF-8 for pasted text)
    byte_length: NonNegativeInt
    media_type: str  # "text/plain; charset=utf-8" or "application/pdf"
    idempotency_key: str  # namespace|external_id|version|sha256
    supersedes_version_id: OpaqueId | None = None


class PageSpan(Frozen):
    page: PositiveInt
    start: NonNegativeInt
    end: NonNegativeInt
    char_count: NonNegativeInt


class TextExtraction(Frozen):
    """Extracted text for one SourceVersion. For pasted text, status is
    not_applicable and ``text`` is the pasted text itself."""

    source_version_id: OpaqueId
    status: ExtractionStatus
    text: str  # clinical content: memory only, never logged
    pages: tuple[PageSpan, ...] = ()
    extractor: str  # "extractor@version", e.g. "pdfplumber@0.11.7" or "paste@1"
    note: str | None = None  # e.g. "page 1 has no text layer"


# ---------------------------------------------------------------------------
# Derived: assertions, changes
# ---------------------------------------------------------------------------


class Span(Frozen):
    start: NonNegativeInt
    end: NonNegativeInt
    page: PositiveInt | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "Span":
        if self.end < self.start:
            raise ValueError("span end < start")
        return self


class Assertion(Frozen):
    """Extraction only; never paraphrase. ``quote`` == extraction.text[start:end]."""

    assertion_id: OpaqueId
    source_version_id: OpaqueId
    span: Span
    quote: str
    fact_type: FactType
    subject_key: SubjectKey  # registry key, e.g. "drug:amlodipine"
    value: str | None = None  # normalised value, e.g. "6.4", "5 mg"
    unit: str | None = None
    frequency: str | None = None  # normalised frequency, e.g. "once_daily"
    response_kinds: tuple[ResponseKind, ...] = ()
    polarity: Polarity
    certainty: Certainty
    scope: AssertionScope = AssertionScope.SPECIFIC
    language: str = "und"
    extractor: str  # "extractor@version"
    review_required: bool = False
    carried_forward_from: OpaqueId | None = None  # assertion_id of the origin
    is_critical: bool = False  # observation beyond a registry critical threshold
    adjudicated: bool = False  # L2: kept, addressable, inactive in detection


class Change(Frozen):
    change_id: OpaqueId
    kind: ChangeKind
    subject_key: SubjectKey
    from_assertion_id: OpaqueId | None  # None for NEW
    to_assertion_id: OpaqueId | None  # None for REMOVED


# ---------------------------------------------------------------------------
# Checks, flags, evidence
# ---------------------------------------------------------------------------


class CheckRun(Frozen):
    run_id: OpaqueId
    encounter_id: OpaqueId
    source_cutoff: UtcDatetime
    ruleset_version: str
    registry_version: str
    source_set_hash: Sha256Hex  # hash over sorted in-scope source_version sha256s
    started_at: UtcDatetime
    completed_at: UtcDatetime
    outcome: CheckRunOutcome


class Evidence(Frozen):
    """Version-bound anchor. Wire name of source_version_id is note_version_id.

    Span evidence cites a SourceVersion. ``encounter_record`` evidence (OWN-001 only) cites a
    structured encounter field instead: no source version, no span, no quote. It is never a
    fake anchor on some note."""

    source_version_id: OpaqueId | None = Field(alias="note_version_id")
    start: NonNegativeInt
    end: NonNegativeInt
    page: PositiveInt | None = None
    quote: str  # == extraction.text[start:end]; "" for extraction_gap
    quote_sha256: Sha256Hex
    role_in_flag: EvidenceRole
    evidence_revision: PositiveInt = 1
    record_field: RecordField | None = None

    @model_validator(mode="after")
    def _grounding_kind(self) -> "Evidence":
        if self.role_in_flag is EvidenceRole.ENCOUNTER_RECORD:
            if (self.record_field is None or self.source_version_id is not None or self.start or self.end
                    or self.page is not None or self.quote):
                raise ValueError("encounter_record evidence names a record field and carries no span")
        elif self.source_version_id is None or self.record_field is not None:
            raise ValueError("span evidence must cite a source version and no record field")
        return self


class Flag(Frozen):
    """Serialises to the appendix flag JSON exactly, plus additive fields."""

    # --- appendix fields (wire names are fixed) ---
    flag_id: FlagIdStr
    tier: Tier
    category: FlagCategory
    title: str
    reason: str
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    owner_staff_id: OpaqueId  # never None: Tier 1 is never unassigned
    check_version: CheckVersionStr
    created_at: UtcDatetime
    # --- additive fields ---
    rule_id: RuleId
    lens: Lens
    subject_key: SubjectKey
    state: FlagState
    revision: PositiveInt  # CAS counter: bumped by every decision and every engine change
    evidence_revision: PositiveInt  # bumped only when the evidence set changes
    affected_contributor_ids: tuple[OpaqueId, ...] = ()
    question: str | None = None  # review question (differencing), never a verdict
    ready_for_clinician: bool = False
    new_evidence_since_decision: bool = False  # L2 reopen marker
    source_changed_since_flag: bool = False  # feedback item 16
    first_run_id: OpaqueId
    last_run_id: OpaqueId


class AbsenceFinding(Frozen):
    """An absence answer is a claim about a SEARCH, not about the patient.
    Cannot be constructed without its search scope."""

    question_template_id: str
    terms_searched: tuple[str, ...] = Field(min_length=1)  # registry keys
    registry_version: str
    sources_searched: tuple["SearchedSource", ...] = Field(min_length=1)
    cutoff: UtcDatetime
    status: Literal[
        BubbleStatus.NOT_DOCUMENTED_IN_SUPPLIED_SOURCES, BubbleStatus.INCOMPLETE_EXTRACTION
    ]

    @model_validator(mode="after")
    def _scope_decides_status(self) -> "AbsenceFinding":
        unread = [s for s in self.sources_searched if s.extraction_status not in ABSENCE_SAFE_EXTRACTION]
        if unread and self.status == BubbleStatus.NOT_DOCUMENTED_IN_SUPPLIED_SOURCES:
            raise ValueError("not_documented is impossible while any in-scope source is not fully extracted")
        if not unread and self.status == BubbleStatus.INCOMPLETE_EXTRACTION:
            raise ValueError("incomplete_extraction requires at least one unread source")
        return self


class SearchedSource(Frozen):
    source_version_id: OpaqueId = Field(alias="note_version_id")
    extraction_status: ExtractionStatus


AbsenceFinding.model_rebuild()


class QuestionBubble(Frozen):
    bubble_id: BubbleIdStr
    question_template_id: str
    question: str  # rendered from the template; a question, never a verdict
    subject_key: SubjectKey
    status: BubbleStatus
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    cutoff: UtcDatetime
    uncertainty_note: str = Field(min_length=1)
    flag_id: FlagIdStr | None = None
    absence: AbsenceFinding | None = None
    rank: PositiveInt  # template rank from the ruleset (deterministic ordering)

    @model_validator(mode="after")
    def _absence_iff_absence_status(self) -> "QuestionBubble":
        is_absence = self.status in (
            BubbleStatus.NOT_DOCUMENTED_IN_SUPPLIED_SOURCES,
            BubbleStatus.INCOMPLETE_EXTRACTION,
        )
        if is_absence != (self.absence is not None):
            raise ValueError("absence finding required exactly for absence statuses")
        if self.absence is not None and self.absence.status != self.status:
            raise ValueError("bubble status must equal its absence finding status")
        return self


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


class EvidenceRef(Frozen):
    """Points at one cited span, e.g. the allergy entry a clinician confirms as correct.
    Clients hold evidence, never assertion ids; the engine maps a ref to its assertion(s)."""

    source_version_id: OpaqueId = Field(alias="note_version_id")
    start: NonNegativeInt
    end: NonNegativeInt


class DecisionRequest(Frozen):
    """What a client sends. Rationale text is held in memory only, never logged."""

    action: DecisionAction
    expected_revision: PositiveInt
    reason_code: ReasonCode | None = None
    rationale_text: str | None = Field(default=None, max_length=2000)
    new_owner_staff_id: OpaqueId | None = None  # reassign
    edit_field: EditField | None = None  # edit
    prepared_check: PreparedCheck | None = None  # mark_ready_for_clinician
    adjudicated_evidence: tuple["EvidenceRef", ...] = ()  # resolve by adjudication (L2): the entry confirmed correct
    duplicate_of_flag_id: FlagIdStr | None = None  # dismiss duplicate_of


class Decision(Frozen):
    """Append-only record of a human decision."""

    decision_id: OpaqueId
    flag_id: FlagIdStr
    encounter_id: OpaqueId
    expected_revision: PositiveInt
    resulting_revision: PositiveInt
    action: DecisionAction
    actor_staff_id: OpaqueId
    actor_role: Role
    reason_code: ReasonCode | None = None
    rationale_text: str | None = None  # memory only
    new_owner_staff_id: OpaqueId | None = None
    edit_field: EditField | None = None
    prepared_check: PreparedCheck | None = None
    adjudicated_evidence: tuple["EvidenceRef", ...] = ()
    from_state: FlagState
    to_state: FlagState
    at: UtcDatetime


class StaleRevision(Frozen):
    """409 body extension: current state and the other actor's decision (feedback 10)."""

    error_code: Literal["stale_revision"] = "stale_revision"
    current_revision: PositiveInt
    current_state: FlagState
    last_decision_action: DecisionAction | None = None
    last_decision_actor_staff_id: OpaqueId | None = None
    last_decision_at: UtcDatetime | None = None


# ---------------------------------------------------------------------------
# Closure and summary
# ---------------------------------------------------------------------------


class ClosureBlocker(Frozen):
    flag_id: FlagIdStr
    tier: Tier
    state: FlagState
    owner_staff_id: OpaqueId
    opened_at: UtcDatetime


class ClosureView(Frozen):
    encounter_id: OpaqueId
    cutoff: UtcDatetime
    status: ClosureStatus
    tier1_blockers: tuple[ClosureBlocker, ...]
    tier2_open: tuple[ClosureBlocker, ...]
    tier3_open_count: NonNegativeInt
    decisions: tuple[Decision, ...]


class TimelineEntry(Frozen):
    source_id: OpaqueId
    source_version_id: OpaqueId = Field(alias="note_version_id")
    version: PositiveInt
    author_staff_id: OpaqueId
    discipline: Discipline
    source_type: SourceType
    source_time: UtcDatetime
    extraction_status: ExtractionStatus
    title: str


class SummaryClaim(Frozen):
    """Every claim is a deterministic template over flag/decision/bubble records,
    with evidence. No free paraphrase."""

    template: SummaryClaimTemplate
    params: dict[str, str | int]  # e.g. {"flag_id": ..., "tier": 1, "owner_staff_id": ...}
    text: str  # rendered from the template
    evidence: tuple[Evidence, ...] = Field(min_length=1)


HUMAN_REVIEW_STATEMENT = (
    "Requires human review. Not the medical record. Does not diagnose or recommend treatment."
)


class Summary(Frozen):
    encounter_id: OpaqueId
    encounter_ref: str
    patient_ref: OpaqueId
    generated_at: UtcDatetime
    cutoff: UtcDatetime
    ruleset_version: str
    registry_version: str
    closure_status: ClosureStatus
    timeline: tuple[TimelineEntry, ...]
    claims: tuple[SummaryClaim, ...]
    human_review_statement: Literal[
        "Requires human review. Not the medical record. Does not diagnose or recommend treatment."
    ] = HUMAN_REVIEW_STATEMENT
    stale_after_source_change: bool = False


# ---------------------------------------------------------------------------
# Audit, feedback, governance
# ---------------------------------------------------------------------------


class AuditEvent(Frozen):
    """Allowlisted fields only (log_allowlist.py). Hash-chained; no content."""

    event_id: OpaqueId
    at: UtcDatetime
    actor_id: OpaqueId | None
    role: Role | None
    action: AuditAction
    target_type: AuditTargetType
    target_id: OpaqueId | None
    outcome: AuditOutcome
    hashes: tuple[Sha256Hex, ...] = ()
    prev_event_hash: Sha256Hex
    event_hash: Sha256Hex


class FeedbackEvent(Frozen):
    """Append-only. No clinical content."""

    feedback_id: OpaqueId
    flag_id: FlagIdStr
    rule_id: RuleId
    rule_version: PositiveInt
    ruleset_version: str
    action: DecisionAction
    reason_code: ReasonCode | None = None
    corrected_owner_staff_id: OpaqueId | None = None
    usefulness: Usefulness | None = None
    time_on_screen_ms: NonNegativeInt | None = None
    actor_role: Role
    at: UtcDatetime


class RuleProposal(Frozen):
    proposal_id: OpaqueId
    kind: ProposalKind
    rule_id: RuleId | None = None
    target_ruleset_version: str
    payload: dict[str, Any]
    rationale_code: str
    evidence_counts: dict[str, int]  # with denominators


class ApprovalRecord(Frozen):
    ruleset_version: str
    ruleset_sha256: Sha256Hex
    registry_version: str
    registry_sha256: Sha256Hex
    evaluation_report_sha256: Sha256Hex | None
    approver_role: Literal["clinical_governance"]
    approver_label: str  # synthetic
    approved_on: str  # ISO date
    status: RulesetStatus


# ---------------------------------------------------------------------------
# Rulesets and term registry (schemas; content filled by B1, approval by B4)
# ---------------------------------------------------------------------------


class Term(Frozen):
    key: SubjectKey  # "<kind>:<name>", e.g. "drug:amlodipine"
    kind: TermKind
    synonyms: tuple[str, ...] = Field(min_length=1)  # lower-case surface forms
    classes: tuple[SubjectKey, ...] = ()  # e.g. allergen:penicillin -> drug_class:penicillins
    unit: str | None = None  # analytes: canonical unit
    critical_high: float | None = None
    critical_low: float | None = None
    deterioration_below: float | None = None
    deterioration_at_or_above: float | None = None
    threshold_status: ThresholdStatus | None = None


class AllergyDenial(Frozen):
    phrase: str  # lower-case, e.g. "nkda"
    scope: Literal[AssertionScope.ALL_DRUGS, AssertionScope.ALL_ALLERGIES]


class FrequencyTerm(Frozen):
    phrase: str  # lower-case surface form, e.g. "bd", "twice daily"
    normalised: str  # e.g. "twice_daily"


class TermRegistry(Frozen):
    registry_version: str
    terms: tuple[Term, ...]
    allergy_denials: tuple[AllergyDenial, ...]
    frequencies: tuple[FrequencyTerm, ...]
    dose_units: tuple[str, ...]  # L4 broad catch: mg, mcg, g, ml, units, tablets, iu
    cues: dict[CueKind, tuple[str, ...]]


class RuleDefinition(Frozen):
    rule_id: RuleId
    version: PositiveInt
    title: str
    category: FlagCategory
    lens: Lens
    default_tier: Tier
    owner_routing: OwnerRouting
    enabled: bool
    protected_floor: bool  # Tier 1 + allergy/medication/critical classes: cannot be lowered or disabled
    registry_term_kinds: tuple[TermKind, ...] = ()
    reason_template: str
    question_template: str | None = None


class BubbleTrigger(Frozen):
    kind: BubbleTriggerKind
    rule_id: RuleId | None = None  # for FLAG_RULE
    analyte_keys: tuple[SubjectKey, ...] = ()  # CRITICAL_OBSERVATION filter; () = any critical analyte


class QuestionTemplate(Frozen):
    template_id: str
    rank: PositiveInt  # deterministic ordering; lower = shown first
    text: str  # may contain {placeholders} filled from registry display names
    trigger: BubbleTrigger
    answer_mode: BubbleAnswerMode
    #: Absence search terms: registry keys, "cue:<CueKind>" references, or "{subject}".
    search_term_keys: tuple[str, ...] = ()


class Ruleset(Frozen):
    ruleset_version: str
    registry_version: str
    rules: tuple[RuleDefinition, ...]
    question_templates: tuple[QuestionTemplate, ...]


class RulesetBundle(Frozen):
    """What the engine receives: a pinned, approved ruleset and its registry."""

    ruleset: Ruleset
    registry: TermRegistry
    ruleset_sha256: Sha256Hex
    registry_sha256: Sha256Hex


# ---------------------------------------------------------------------------
# Engine input/output
# ---------------------------------------------------------------------------


class EncounterSnapshot(Frozen):
    """Everything the (pure) engine needs. Built by the API from the workspace store.
    Contains clinical content: memory only."""

    clinic: Clinic
    patient: Patient
    encounter: Encounter
    staff: tuple[Staff, ...]
    memberships: tuple[CareTeamMembership, ...]
    sources: tuple[Source, ...]
    versions: tuple[SourceVersion, ...]
    extractions: tuple[TextExtraction, ...]
    prior_flags: tuple[Flag, ...] = ()  # current state of every flag from earlier runs
    decisions: tuple[Decision, ...] = ()  # append-only history


class CheckRunResult(Frozen):
    run: CheckRun
    flags: tuple[Flag, ...]  # every flag known for the encounter, current state
    assertions: tuple[Assertion, ...]
    changes: tuple[Change, ...]


# ---------------------------------------------------------------------------
# Audio-ready schema (NOT BUILT; Section 7)
# ---------------------------------------------------------------------------


class AudioAsset(Frozen):
    audio_asset_id: OpaqueId
    encounter_id: OpaqueId
    consent_status: ConsentStatus
    consent_recorded_at: UtcDatetime | None = None
    sha256: Sha256Hex


class Transcript(Frozen):
    transcript_id: OpaqueId
    version: PositiveInt
    audio_asset_id: OpaqueId
    supersedes_version: PositiveInt | None = None


class TranscriptSegment(Frozen):
    """A segment maps onto a SourceVersion (source_type transcript_segment) with spans,
    so rules need no change when audio arrives."""

    transcript_id: OpaqueId
    transcript_version: PositiveInt
    segment_index: NonNegativeInt
    speaker_label: str  # diarisation label, e.g. "SPEAKER_1"
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt
    transcription_confidence: float = Field(ge=0.0, le=1.0)
    source_version_id: OpaqueId  # the SourceVersion carrying the segment text
    text_span: Span


# ---------------------------------------------------------------------------
# Session / identity (demonstrator)
# ---------------------------------------------------------------------------


class SessionInfo(Frozen):
    staff_id: OpaqueId
    display_name: str
    role: Role
    discipline: Discipline


class WorkspaceInfo(Frozen):
    """The workspace token lives only in JS memory (Section 6.3)."""

    workspace_token: str
    encounter_ids: tuple[OpaqueId, ...]
    expires_at: UtcDatetime
    single_process_store: Literal[True] = True


__all__ = [name for name in dir() if not name.startswith("_")]
