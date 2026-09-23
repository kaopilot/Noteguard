import { useRef, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { Flag, FlagDetail } from '../api/types';
import { humanize } from '../lib/labels';
import { mayRecordFeedback } from '../lib/permissions';
import { useTimeOnScreen } from '../lib/timeOnScreen';
import { sgtDateTime } from '../lib/time';
import { useEnc } from './ctx';
import { EvidenceItem } from './EvidenceItem';
import { Feedback } from './Feedback';
import { TierBadge } from './TierBadge';

export function FlagCard({ flag, blocksClosure, canDecide, onDecide, focused, slot, decided = false }: {
  flag: Flag;
  blocksClosure: boolean;
  canDecide: boolean;
  onDecide: (f: Flag) => void;
  focused: boolean;
  slot?: ReactNode;
  /** At least one human decision exists (from the closure view), so usefulness feedback can attach. */
  decided?: boolean;
}) {
  const { staffName, view, me } = useEnc();
  const cardRef = useRef<HTMLElement | null>(null);
  const timeOnScreen = useTimeOnScreen(cardRef);
  const [history, setHistory] = useState<FlagDetail | 'loading' | 'unavailable' | null>(null);
  const headingId = `flag-${flag.flag_id}`;

  const loadHistory = async () => {
    if (history !== null && history !== 'unavailable') {
      setHistory(null);
      return;
    }
    setHistory('loading');
    const r = await api<FlagDetail>('GET', 'FLAG', { encounter_id: view.encounter.encounter_id, flag_id: flag.flag_id });
    setHistory(r.ok ? r.data : 'unavailable');
  };

  return (
    <article ref={cardRef} className={`flag flag-t${flag.tier}${focused ? ' flag-focused' : ''}`} aria-labelledby={headingId} id={`card-${flag.flag_id}`}>
      <header className="flag-head">
        <TierBadge tier={flag.tier} />
        <h3 id={headingId}>{flag.title}</h3>
      </header>
      <dl className="flag-facts">
        <div><dt>Owner</dt><dd>{staffName(flag.owner_staff_id)}</dd></div>
        <div><dt>Status</dt><dd>{humanize(flag.state)}</dd></div>
        <div><dt>Closure</dt><dd>{blocksClosure ? 'Blocks closure' : 'Does not block closure'}</dd></div>
      </dl>
      {(flag.source_changed_since_flag || flag.new_evidence_since_decision || flag.ready_for_clinician) && (
        <ul className="flag-markers">
          {flag.source_changed_since_flag && <li>Source changed since flag: a newer version of a cited note exists</li>}
          {flag.new_evidence_since_decision && <li>New evidence since the last decision</li>}
          {flag.ready_for_clinician && <li>Marked ready for clinician</li>}
        </ul>
      )}
      <p className="flag-reason">{flag.reason}</p>
      {flag.question && <p className="flag-question">{flag.question}</p>}
      {flag.state === 'superseded' && (
        <p className="flag-superseded">
          A later check superseded this flag. It stays visible until a person confirms it by resolving it with a reason.
        </p>
      )}
      <ul className="ev-list">
        {flag.evidence.map((ev, i) => <EvidenceItem key={i} ev={ev} all={flag.evidence} />)}
      </ul>
      {flag.affected_contributor_ids.length > 0 && (
        <p className="flag-contributors">Also involves {flag.affected_contributor_ids.map((id) => staffName(id)).join(', ')}</p>
      )}
      <div className="flag-actions">
        {canDecide && <button type="button" className="btn btn-primary" onClick={() => onDecide(flag)}>Decide</button>}
        <button type="button" className="btn btn-quiet" onClick={loadHistory} aria-expanded={history !== null && history !== 'unavailable'}>
          {history !== null && history !== 'unavailable' ? 'Hide history' : 'History'}
        </button>
      </div>
      {slot}
      {decided && mayRecordFeedback(me, view, flag) && <Feedback flag={flag} timeOnScreen={timeOnScreen} />}
      {history === 'loading' && <p className="note note-quiet">Loading history…</p>}
      {history === 'unavailable' && <p className="note note-problem">History could not be loaded.</p>}
      {history !== null && typeof history === 'object' && (
        <ol className="flag-history">
          {history.revisions.map((r) => (
            <li key={r.revision}>
              Revision {r.revision}: {humanize(r.state)}, owner {staffName(r.owner_staff_id)}, {sgtDateTime(r.at)}
              {r.decision_id ? ' (human decision)' : ' (check run)'}
            </li>
          ))}
          {history.decisions.map((d) => (
            <li key={d.decision_id}>
              {staffName(d.actor_staff_id)}: {humanize(d.action)}{d.reason_code ? `, reason ${humanize(d.reason_code)}` : ''}, {sgtDateTime(d.at)}
            </li>
          ))}
        </ol>
      )}
      <p className="flag-provenance">
        Revision {flag.revision}; check version {flag.check_version}; raised {sgtDateTime(flag.created_at)}
      </p>
    </article>
  );
}
