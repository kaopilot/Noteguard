import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { AggregateView } from '../api/types';
import { humanize } from '../lib/labels';
import { sgtDateTime } from '../lib/time';
import { Loaded, toLoadable, type Loadable } from './States';
import { TierBadge } from './TierBadge';

/** Aggregate flag patterns for governance roles. Counts are shown exactly as served: no totals or
 * re-derived numbers, because adding cells around a suppressed "<5" can reveal it. No patient or
 * encounter identifiers exist in this view (B4 / Section 11). */
export function Aggregate() {
  const [data, setData] = useState<Loadable<AggregateView>>({ kind: 'loading' });
  const load = useCallback(async () => {
    setData({ kind: 'loading' });
    setData(toLoadable(await api<AggregateView>('GET', 'AGGREGATE')));
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <main className="screen aggregate">
      <h1>Flag patterns across encounters</h1>
      <p className="note note-quiet">
        Counts of flags by rule, tier, status and how long they have been open. No note text, patient or encounter details are
        included. For governance review only.
      </p>
      <Loaded value={data} what="The aggregate report" noRun={<p className="note note-quiet">No aggregate report is available yet.</p>}>
        {(v) => <AggregateTable v={v} onRefresh={() => void load()} />}
      </Loaded>
      {data.kind === 'error' && data.status === 403 && (
        <p className="note note-problem" role="alert">Your role cannot view aggregate reports.</p>
      )}
    </main>
  );
}

function AggregateTable({ v, onRefresh }: { v: AggregateView; onRefresh: () => void }) {
  const rows = useMemo(
    () => [...v.cells].sort((a, b) => a.tier - b.tier || a.rule_id.localeCompare(b.rule_id) || a.state.localeCompare(b.state) || a.age_bucket.localeCompare(b.age_bucket)),
    [v.cells],
  );
  const hasResponse = v.cells.some((c) => c.response_time_bucket != null);
  return (
    <>
      <dl className="summary-facts">
        <div><dt>Generated</dt><dd>{sgtDateTime(v.generated_at)}</dd></div>
        <div><dt>Rule set</dt><dd>{v.ruleset_version}</dd></div>
        <div><dt>Small counts</dt><dd>Fewer than {v.small_cell_threshold} are shown as “&lt;{v.small_cell_threshold}”</dd></div>
      </dl>
      <p className="note note-quiet">No totals are shown: small counts are suppressed, and adding the other cells would reveal them.</p>
      {rows.length === 0 ? (
        <p className="note note-quiet">No flags have been recorded on this demonstrator yet.</p>
      ) : (
        <div className="table-wrap" role="region" aria-label="Aggregate counts" tabIndex={0}>
          <table className="aggregate-table">
            <thead>
              <tr>
                <th scope="col">Rule</th><th scope="col">Tier</th><th scope="col">Status</th><th scope="col">Open for</th>
                {hasResponse && <th scope="col">Time to first decision</th>}
                <th scope="col">Flags</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => (
                <tr key={`${c.rule_id}-${c.state}-${c.age_bucket}-${c.response_time_bucket ?? ''}-${i}`}>
                  <td>{c.rule_id}</td><td><TierBadge tier={c.tier} /></td><td>{humanize(c.state)}</td><td>{c.age_bucket}</td>
                  {hasResponse && <td>{c.response_time_bucket ? humanize(c.response_time_bucket) : '—'}</td>}
                  <td className="aggregate-count">{c.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button type="button" className="btn btn-quiet" onClick={onRefresh}>Refresh</button>
    </>
  );
}
