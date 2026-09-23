import { useState } from 'react';
import { api } from '../api/client';
import type { ClosureView } from '../api/types';
import { CLOSURE_STATUS, humanize } from '../lib/labels';
import { mayCloseEncounter } from '../lib/permissions';
import { age, sgtDateTime } from '../lib/time';
import { useEnc } from './ctx';
import { Loaded, type Loadable } from './States';
import { TierBadge } from './TierBadge';

type Blocker = ClosureView['tier1_blockers'][number];

export function Closure({ closure, onReviewTier3 }: { closure: Loadable<ClosureView>; onReviewTier3: () => void }) {
  const { me, view, staffName, flagById, openFlag, openSource } = useEnc();
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const attempt = async () => {
    setBusy(true);
    const r = await api<ClosureView>('POST', 'CLOSURE', { encounter_id: view.encounter.encounter_id });
    setBusy(false);
    if (r.ok) setResult('No Tier 1 item blocks closure at this cutoff. Noteguard is read-only: closing the record in the EMR remains your action.');
    else if (r.errorCode === 'closure_blocked') setResult('Closure is blocked. The server lists what blocks it below; a check run must also cover every source version.');
    else if (r.status === 501) setResult('Closing is not available in this build.');
    else setResult(`The server did not allow closure (code ${r.errorCode}).`);
  };

  const row = (b: Blocker) => {
    const ev = flagById(b.flag_id)?.evidence ?? [];
    const first = ev.find((e) => e.note_version_id !== null);
    return (
    <li key={b.flag_id} className="closure-item">
      <TierBadge tier={b.tier} />
      <div>
        <button type="button" className="link" onClick={() => openFlag(b.flag_id)}>{flagById(b.flag_id)?.title ?? 'Flag'}</button>
        <p>{humanize(b.state)}; owner {staffName(b.owner_staff_id)}; open since {sgtDateTime(b.opened_at)} ({age(b.opened_at)})</p>
        {first?.note_version_id && (
          <button type="button" className="link" onClick={() => openSource({ versionId: first.note_version_id ?? '', evidence: ev })}>Show evidence</button>
        )}
      </div>
    </li>
    );
  };

  return (
    <section className="closure" aria-label="Closure">
      <Loaded value={closure} what="Closure view">
        {(c) => (
          <>
            <h2 className={`closure-headline closure-${c.status}`}>{CLOSURE_STATUS[c.status].headline}</h2>
            <p>{CLOSURE_STATUS[c.status].detail} Cutoff {sgtDateTime(c.cutoff)}.</p>
            <h3>Blocking closure (Tier 1)</h3>
            {c.tier1_blockers.length ? <ol className="closure-list">{c.tier1_blockers.map(row)}</ol> : <p className="note note-quiet">None.</p>}
            <h3>Open Tier 2</h3>
            {c.tier2_open.length ? <ol className="closure-list">{c.tier2_open.map(row)}</ol> : <p className="note note-quiet">None.</p>}
            <h3>Tier 3</h3>
            <p>
              {c.tier3_open_count} open.{' '}
              {c.tier3_open_count > 0 && <button type="button" className="link" onClick={onReviewTier3}>Review Tier 3 items</button>}
            </p>
            <h3>Decisions</h3>
            {c.decisions.length === 0 ? <p className="note note-quiet">No decisions recorded yet.</p> : (
              <div className="table-wrap">
                <table className="decisions">
                  <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">Decision</th><th scope="col">Reason code</th><th scope="col">Flag</th></tr></thead>
                  <tbody>
                    {c.decisions.map((d) => (
                      <tr key={d.decision_id}>
                        <td>{sgtDateTime(d.at)}</td>
                        <td>{staffName(d.actor_staff_id)}</td>
                        <td>{humanize(d.action)} ({humanize(d.from_state).toLowerCase()} to {humanize(d.to_state).toLowerCase()})</td>
                        <td>{d.reason_code ? humanize(d.reason_code) : 'None'}</td>
                        <td>{flagById(d.flag_id)?.title ?? d.flag_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {mayCloseEncounter(me, view) && (
              <div className="closure-action">
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void attempt()}>Check closure now</button>
                {result && <p className="note note-change" role="status">{result}</p>}
              </div>
            )}
          </>
        )}
      </Loaded>
    </section>
  );
}
