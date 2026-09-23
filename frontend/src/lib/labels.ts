// Display wording for server-provided values. Keys are typed against the generated wire types, so
// TypeScript fails the build if the contract adds a value this file does not describe. These maps
// only choose words; tiers, owners, states and closure always come from the server.
import type {
  AIDraftStatus, BubbleStatus, ChangeKind, Usefulness, ClosureStatus, DecisionAction, Discipline, EvidenceRole, ExtractionStatus, SourceType, Tier,
} from '../api/types';

/** 'already_addressed_in_source' -> 'Already addressed in source'. */
export function humanize(value: string): string {
  const s = value.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Past tense of a decision action, for sentences such as "Dr Lim accepted this flag". */
export const DID: Record<DecisionAction, string> = {
  accept: 'accepted',
  edit: 'edited',
  reassign: 'reassigned',
  mark_ready_for_clinician: 'marked ready for clinician',
  dismiss: 'dismissed',
  resolve: 'resolved',
};

/** AI drafting status wording (Section 9, L10; matches B4's governance/ai_drafting.py). */
export const AI_STATUS: Record<AIDraftStatus, string> = {
  disabled: 'AI drafting disabled.',
  unavailable_fallback: 'AI drafting unavailable; showing rule explanation.',
  rejected_fallback: 'AI draft discarded by its validator; showing rule explanation.',
  validated: 'AI-drafted wording, checked against the cited quotes.',
};

/** Shown when the server refuses rule-dependent work because the rule set is not approved (503
 * ruleset_unapproved, B4's approval check). A governance state, not an outage. */
export const RULESET_PAUSED = 'the rule set is awaiting clinical governance approval.';

/** Usefulness feedback wording. Feedback informs offline governance review only (Section 11). */
export const USEFULNESS: Record<Usefulness, string> = {
  useful: 'Useful',
  not_useful: 'Not useful',
  wrong_owner: 'Wrong owner',
  stale_wording: 'Wording out of date',
  missing_rule: 'A related concern was not flagged',
};

export type TierShape = 'octagon' | 'triangle' | 'circle';
export const TIER: Record<Tier, { label: string; shape: TierShape; hint: string }> = {
  1: { label: 'Tier 1', shape: 'octagon', hint: 'Potential immediate safety or closure risk' },
  2: { label: 'Tier 2', shape: 'triangle', hint: 'Continuity or follow-up gap' },
  3: { label: 'Tier 3', shape: 'circle', hint: 'Documentation quality' },
};

export const EVIDENCE_ROLE: Record<EvidenceRole, string> = {
  claim: 'Cited statement',
  counter_claim: 'Other statement',
  origin: 'Earlier wording',
  suppressor: 'Documented response',
  trigger: 'Prompting statement',
  extraction_gap: 'Unread page',
  missing_response_window: 'Response window',
  encounter_record: 'Care-team record',
};

export const BUBBLE_STATUS: Record<BubbleStatus, string> = {
  documented: 'Documented in the cited source',
  not_documented_in_supplied_sources: 'Not documented in the supplied sources',
  conflicting: 'Sources disagree',
  incomplete_extraction: 'Incomplete extraction: cannot answer yet',
  requires_human_review: 'Needs a person to check',
};

export const CLOSURE_STATUS: Record<ClosureStatus, { headline: string; detail: string }> = {
  blocked: { headline: 'Closure blocked', detail: 'At least one Tier 1 item needs a clinician decision.' },
  clear_with_open_tier2: { headline: 'No Tier 1 blocks closure', detail: 'Tier 2 items are still open.' },
  clear: { headline: 'No Tier 1 or Tier 2 items open', detail: 'At this cutoff, nothing blocks closure.' },
};

export const CHANGE_KIND: Record<ChangeKind, { sign: string; label: string }> = {
  new: { sign: '+', label: 'new' },
  explicit_change: { sign: '~', label: 'explicit change' },
  reworded: { sign: '\u2248', label: 'reworded' },
  carried_forward: { sign: '=', label: 'carried forward' },
  removed: { sign: '\u2212', label: 'removed' },
};

export const DISCIPLINE: Record<Discipline, string> = {
  clinician: 'Clinician',
  nursing: 'Nursing',
  physiotherapy: 'Physiotherapy',
  counselling_social_work: 'Counselling and social work',
  pharmacy: 'Pharmacy',
  other: 'Other',
};

export const SOURCE_TYPE: Record<SourceType, string> = {
  pasted_text: 'Pasted note',
  pdf: 'PDF',
  fhir_documentreference: 'FHIR document',
  hl7v2: 'HL7 v2 message',
  cda: 'CDA document',
  transcript_segment: 'Transcript segment',
};

export const EXTRACTION: Record<ExtractionStatus, string> = {
  complete: 'Text fully extracted',
  partial: 'Text partly extracted',
  no_text_layer: 'No text layer',
  failed: 'Extraction did not complete',
  not_applicable: 'Typed text',
};

/** Display name of a registry subject key: the part after the kind prefix, underscores as spaces. */
export function subjectName(subjectKey: string): string {
  const i = subjectKey.indexOf(':');
  return (i >= 0 ? subjectKey.slice(i + 1) : subjectKey).replace(/_/g, ' ');
}
