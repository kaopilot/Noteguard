import { useId, useState } from 'react';
import { api, type ErrorCode } from '../api/client';
import { usefulnessValues } from '../api/schema.gen';
import type { FeedbackEvent, FeedbackRequest, Flag, Usefulness } from '../api/types';
import { USEFULNESS } from '../lib/labels';
import { useEnc } from './ctx';

const ERROR_TEXT: Partial<Record<ErrorCode, string>> = {
  invalid_transition: 'Feedback opens once a decision has been recorded on this flag.',
  reassign_target_invalid: 'That person is not an active member of this care team.',
  forbidden_role: 'Your role cannot send feedback on this flag.',
  not_found: 'This flag is no longer in the workspace.',
  not_implemented: 'Feedback is not available in this build.',
};

/** One usefulness answer per flag per person per workspace (the server accepts repeats; the UI does
 * not send them, so governance counts are not inflated). */
export function Feedback({ flag, timeOnScreen }: { flag: Flag; timeOnScreen: () => number | null }) {
  const { view, staffName } = useEnc();
  const id = useId();
  const [choice, setChoice] = useState<Usefulness | ''>('');
  const [owner, setOwner] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<FeedbackEvent | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const members = view.staff.filter((s) => view.memberships.some((m) => m.staff_id === s.staff_id) && s.staff_id !== flag.owner_staff_id);

  if (sent) {
    return (
      <p className="feedback-sent" role="status">
        Feedback recorded: {USEFULNESS[sent.usefulness ?? (choice as Usefulness)]}
        {sent.corrected_owner_staff_id ? ` (should be ${staffName(sent.corrected_owner_staff_id)})` : ''}. It informs governance
        review of the rules; it does not change this flag.
      </p>
    );
  }
  const send = async () => {
    if (choice === '') return;
    const body: FeedbackRequest = {
      flag_id: flag.flag_id,
      usefulness: choice,
      time_on_screen_ms: timeOnScreen(),
      corrected_owner_staff_id: choice === 'wrong_owner' && owner !== '' ? owner : null,
    };
    setBusy(true);
    setProblem(null);
    const r = await api<FeedbackEvent>('POST', 'FEEDBACK', { encounter_id: view.encounter.encounter_id }, body);
    setBusy(false);
    if (r.ok) setSent(r.data);
    else setProblem(ERROR_TEXT[r.errorCode as ErrorCode] ?? `Feedback was not recorded (server code ${r.errorCode}).`);
  };
  return (
    <form className="feedback" aria-labelledby={`${id}-q`} onSubmit={(e) => { e.preventDefault(); void send(); }}>
      <p id={`${id}-q`} className="feedback-q">Was this flag useful? <small>Goes to governance review; does not change the flag.</small></p>
      <div className="feedback-options" role="radiogroup" aria-labelledby={`${id}-q`}>
        {usefulnessValues.map((u) => (
          <label key={u} className="feedback-option">
            <input type="radio" name={`${id}-u`} value={u} checked={choice === u} onChange={() => setChoice(u)} />
            <span>{USEFULNESS[u]}</span>
          </label>
        ))}
      </div>
      {choice === 'wrong_owner' && (
        <div className="field">
          <label htmlFor={`${id}-owner`}>Who should own it? (optional)</label>
          <select id={`${id}-owner`} value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">Not sure</option>
            {members.map((s) => <option key={s.staff_id} value={s.staff_id}>{s.display_name}</option>)}
          </select>
        </div>
      )}
      {problem && <p className="note note-problem" role="alert">{problem}</p>}
      <button type="submit" className="btn btn-quiet" disabled={choice === '' || busy}>{busy ? 'Sending…' : 'Send feedback'}</button>
    </form>
  );
}
