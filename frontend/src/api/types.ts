// Wire types, re-exported from the generated schema (never hand-written; `make types`).
import type { components } from './schema.gen';

type S = components['schemas'];
export type AIStatusView = S['AIStatusView'];
export type AIDraftStatus = S['AIDraftStatus'];
export type AddTextSourceRequest = S['AddTextSourceRequest'];
export type BubbleList = S['BubbleList'];
export type BubbleStatus = S['BubbleStatus'];
export type ChangeKind = S['ChangeKind'];
export type ChangeView = S['ChangeView'];
export type CheckRunView = S['CheckRunView'];
export type ClosureStatus = S['ClosureStatus'];
export type ClosureView = S['ClosureView'];
export type Decision = S['Decision'];
export type DecisionAction = S['DecisionAction'];
export type DecisionRequest = S['DecisionRequest'];
export type Discipline = S['Discipline'];
export type DocumentTokenView = S['DocumentTokenView'];
export type EditField = S['EditField'];
export type EncounterListItem = S['EncounterListItem'];
export type EncounterView = S['EncounterView'];
export type Evidence = S['Evidence'];
export type EvidenceRole = S['EvidenceRole'];
export type FeedbackEvent = S['FeedbackEvent'];
export type FeedbackRequest = S['FeedbackRequest'];
export type ExtractionStatus = S['ExtractionStatus'];
export type Flag = S['Flag'];
export type FlagDetail = S['FlagDetail'];
export type FlagState = S['FlagState'];
export type GlanceView = S['GlanceView'];
export type PreparedCheck = S['PreparedCheck'];
export type QuestionBubble = S['QuestionBubble'];
export type ReasonCode = S['ReasonCode'];
export type Role = S['Role'];
export type SessionView = S['SessionView'];
export type SourceText = S['SourceText'];
export type SourceType = S['SourceType'];
export type SourceView = S['SourceView'];
export type StaleRevision = S['StaleRevision'];
export type Staff = S['Staff'];
export type Summary = S['Summary'];
export type SummaryClaim = S['SummaryClaim'];
export type Tier = S['Tier'];
export type Usefulness = S['Usefulness'];

// LOCAL STAND-IN until CCR-04 part 1 lands (approved 23 Sep; `response_model=AggregateView` on B4's
// route, then `make types`). Mirrors contracts/api_models.py AggregateView/AggregateCell field for
// field, typed with generated enums; replace with S['AggregateView'] / S['AggregateCell'] then.
// `response_time_bucket` is CCR-04 part 2 (optional until B4 fills it).
export type AggregateCell = {
  rule_id: string;
  tier: Tier;
  state: S['FlagState'];
  age_bucket: string;
  count: string;
  response_time_bucket?: string | null;
};
export type AggregateView = {
  generated_at: string;
  ruleset_version: string;
  cells: AggregateCell[];
  small_cell_threshold: number;
};
export type WorkspaceInfo = S['WorkspaceInfo'];
