import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { api, type ErrorCode } from '../api/client';
import { CONTRACT } from '../api/contract-data.gen';
import { decisionActionValues, editFieldValues, preparedCheckValues } from '../api/schema.gen';
import type {
  DecisionAction, DecisionRequest, EditField, Flag, FlagDetail, FlagState, PreparedCheck, ReasonCode,
} from '../api/types';
import { DID, humanize } from '../lib/labels';
import { offeredActions } from '../lib/permissions';
import { sgtDateTime } from '../lib/time';
import { useEnc } from './ctx';
import { TierBadge } from './TierBadge';

const D = CONTRACT.decisions;
const ACTION_HELP: Record<DecisionAction, string> = {
  accept: 'Records that you take responsibility. Accepting does not resolve the flag.',
  edit: 'Change the owner, explanation or resolution note. A rationale is required.',
  reassign: 'Hand the flag to another care-team member. A rationale is required.',
  mark_ready_for_clinician: 'Staff prepare, clinicians close: attach the check you performed.',
  dismiss: 'Dismiss with a reason code. Tier 1 can only be dismissed by the responsible clinician.',
  resolve: 'Resolve with a reason code. Accepted is not resolved.',
};
const ERROR_TEXT: Partial<Record<ErrorCode, string>> = {
  forbidden_role: 'Your role or relationship to this flag does not allow this action. The server refused it.',
  reason_code_required: 'Choose a reason code.',
  reason_code_not_allowed: 'That reason code is not allowed for this action or rule.',
  rationale_required: 'Write a rationale for this action.',
  adjudication_required: 'Choose which cited entry is correct.',
  reassign_target_invalid: 'The new owner must be a care-team member who can own this tier.',
  tier1_cannot_be_deferred: 'Tier 1 flags cannot be deferred.',
  invalid_transition: 'This action is not available from the flag’s current state. Close and refresh.',
  bulk_not_supported: 'Decisions are made one flag at a time.',
  validation_failed: 'The server could not accept this decision as entered.',
  not_implemented: 'Decisions are not available in this build (501).',
  workspace_expired: 'This workspace has expired. Start a fresh case.',
};

type StaleBody = {
  current_revision?: number;
  current_state?: FlagState;
  last_decision_action?: DecisionAction | null;
  last_decision_actor_staff_id?: string | null;
  last_decision_at?: string | null;
};

export function DecisionSheet({ flag, otherFlags, onClose, onDecided, onStale }: {
  flag: Flag;
  otherFlags: readonly Flag[];
  onClose: () => void;
  onDecided: (d: FlagDetail) => void;
  onStale: () => void;
}) {
  const { me, view, staffName } = useEnc();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const actions = useMemo(() => offeredActions(me, view, flag, decisionActionValues), [me, view, flag]);
  const [action, setAction] = useState<DecisionAction | null>(actions[0] ?? null);
  const [reason, setReason] = useState<ReasonCode | ''>('');
  const [rationale, setRationale] = useState('');
  const [editField, setEditField] = useState<EditField | ''>('');
  const [owner, setOwner] = useState('');
  const [check, setCheck] = useState<PreparedCheck | ''>('');
  const [adjudicated, setAdjudicated] = useState<number | null>(null);
  const [duplicateOf, setDuplicateOf] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const reasons: readonly string[] = useMemo(() => {
    if (!action) return [];
    const byAction = (D.reasons_by_action as Record<string, readonly string[]>)[action] ?? [];
    if (action !== 'resolve') return byAction;
    const byRule = (D.resolve_reasons_by_rule as Record<string, readonly string[]>)[flag.rule_id] ?? [];
    return byAction.filter((r) => byRule.includes(r));
  }, [action, flag.rule_id]);

  const needsReason = action !== null && (D.reason_required as readonly string[]).includes(action);
  const needsRationale = action !== null && (D.rationale_required as readonly string[]).includes(action);
  const isAdjudication = reason !== '' && (D.adjudication_reasons as readonly string[]).includes(reason);
  const isDuplicate = reason === 'duplicate_of';
  const targetRoles = (D.reassign_target_roles as Record<string, readonly string[]>)[String(flag.tier)] ?? [];
  const owners = view.staff.filter((s) =>
    s.staff_id !== flag.owner_staff_id
    && targetRoles.includes(s.role)
    && view.memberships.some((m) => m.staff_id === s.staff_id));
  const spanEvidence = flag.evidence.filter((e) => e.note_version_id !== null && e.quote !== '');

  const choose = (a: DecisionAction) => {
    setAction(a);
    setReason('');
    setAdjudicated(null);
    setProblem(null);
  };

  const submit = async () => {
    if (!action) return;
    const adj = isAdjudication && adjudicated !== null ? spanEvidence[adjudicated] : undefined;
    const body: DecisionRequest = {
      action,
      expected_revision: flag.revision,
      adjudicated_evidence: adj && adj.note_version_id ? [{ note_version_id: adj.note_version_id, start: adj.start, end: adj.end }] : [],
      reason_code: reason === '' ? null : reason,
      rationale_text: rationale.trim() === '' ? null : rationale,
      edit_field: editField === '' ? null : editField,
      new_owner_staff_id: owner === '' ? null : owner,
      prepared_check: check === '' ? null : check,
      duplicate_of_flag_id: isDuplicate && duplicateOf !== '' ? duplicateOf : null,
    };
    setBusy(true);
    setProblem(null);
    const r = await api<FlagDetail>('POST', 'FLAG_DECISIONS', { encounter_id: view.encounter.encounter_id, flag_id: flag.flag_id }, body);
    setBusy(false);
    if (r.ok) {
      onDecided(r.data);
      return;
    }
    if (r.errorCode === 'stale_revision') {
      const b = (r.body ?? {}) as StaleBody;
      const who = b.last_decision_actor_staff_id ? staffName(b.last_decision_actor_staff_id) : 'Someone';
      const what = b.last_decision_action ? DID[b.last_decision_action] : 'changed';
      const when = b.last_decision_at ? ` at ${sgtDateTime(b.last_decision_at)}` : '';
      const now = b.current_state ? ` It is now ${humanize(b.current_state).toLowerCase()} (revision ${b.current_revision ?? '?'}).` : '';
      setProblem(`${who} ${what} this flag${when} before your decision was sent.${now} Your decision was not recorded; review the current flag and decide again.`);
      onStale();
      return;
    }
    setProblem(ERROR_TEXT[r.errorCode as ErrorCode] ?? `The server did not record this decision (code ${r.errorCode}).`);
  };

  const ready = action !== null
    && (!needsReason || reason !== '')
    && (!needsRationale || rationale.trim() !== '')
    && (!isAdjudication || adjudicated !== null)
    && (!isDuplicate || duplicateOf !== '')
    && (action !== 'edit' || editField !== '')
    && (action !== 'reassign' || owner !== '')
    && (action !== 'mark_ready_for_clinician' || check !== '');

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={panel} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" aria-hidden="true" />
        <header className="sheet-head">
          <TierBadge tier={flag.tier} />
          <h2 id={titleId}>Decide: {flag.title}</h2>
          <button type="button" className="btn btn-quiet" onClick={onClose}>Close</button>
        </header>
        <p className="sheet-sub">Owner {staffName(flag.owner_staff_id)}; {humanize(flag.state).toLowerCase()}; revision {flag.revision}. One flag per decision.</p>
        {actions.length === 0 ? (
          <p className="note note-quiet">No decision is available to you on this flag.</p>
        ) : (
          <form className="decision-form" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <fieldset>
              <legend>Action</legend>
              {actions.map((a) => (
                <label key={a} className="choice">
                  <input type="radio" name="decision-action" value={a} checked={action === a} onChange={() => choose(a)} />
                  <span><strong>{humanize(a)}</strong><small>{ACTION_HELP[a]}</small></span>
                </label>
              ))}
            </fieldset>
            {reasons.length > 0 && (
              <label className="field">
                <span>Reason code{needsReason ? ' (required)' : ''}</span>
                <select value={reason} onChange={(e) => { setReason(e.target.value as ReasonCode | ''); setAdjudicated(null); }}>
                  <option value="">Choose a reason</option>
                  {reasons.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
                </select>
              </label>
            )}
            {isAdjudication && (
              <fieldset>
                <legend>Which cited entry is correct?</legend>
                {spanEvidence.map((e, i) => (
                  <label key={i} className="choice">
                    <input type="radio" name="adjudicated" checked={adjudicated === i} onChange={() => setAdjudicated(i)} />
                    <span className="record-text">{e.quote}</span>
                  </label>
                ))}
              </fieldset>
            )}
            {isDuplicate && (
              <label className="field">
                <span>Duplicate of</span>
                <select value={duplicateOf} onChange={(e) => setDuplicateOf(e.target.value)}>
                  <option value="">Choose the other flag</option>
                  {otherFlags.filter((f) => f.flag_id !== flag.flag_id).map((f) => (
                    <option key={f.flag_id} value={f.flag_id}>{f.title}</option>
                  ))}
                </select>
              </label>
            )}
            {action === 'edit' && (
              <label className="field">
                <span>What to edit</span>
                <select value={editField} onChange={(e) => setEditField(e.target.value as EditField | '')}>
                  <option value="">Choose</option>
                  {editFieldValues.map((f) => <option key={f} value={f}>{humanize(f)}</option>)}
                </select>
              </label>
            )}
            {action === 'reassign' && (
              <label className="field">
                <span>New owner</span>
                <select value={owner} onChange={(e) => setOwner(e.target.value)}>
                  <option value="">Choose a care-team member</option>
                  {owners.map((s) => <option key={s.staff_id} value={s.staff_id}>{s.display_name}</option>)}
                </select>
              </label>
            )}
            {action === 'mark_ready_for_clinician' && (
              <label className="field">
                <span>Check performed</span>
                <select value={check} onChange={(e) => setCheck(e.target.value as PreparedCheck | '')}>
                  <option value="">Choose</option>
                  {preparedCheckValues.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
                </select>
              </label>
            )}
            {action !== null && action !== 'accept' && (
              <label className="field">
                <span>Rationale{needsRationale ? ' (required)' : ' (optional)'}</span>
                <textarea value={rationale} maxLength={2000} rows={3} onChange={(e) => setRationale(e.target.value)} />
                <small>Sent with this decision only. Not stored on this device.</small>
              </label>
            )}
            {problem && <p className="note note-problem" role="alert">{problem}</p>}
            <div className="sheet-actions">
              <button type="submit" className="btn btn-primary" disabled={!ready || busy}>
                {busy ? 'Recording…' : action ? `Record: ${humanize(action).toLowerCase()}` : 'Record decision'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
