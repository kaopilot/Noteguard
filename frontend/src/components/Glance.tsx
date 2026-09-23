import type { BubbleList, ClosureView, Flag, GlanceView } from '../api/types';
import { BUBBLE_STATUS, CLOSURE_STATUS, humanize } from '../lib/labels';
import { sgtDateTime, sgtTime } from '../lib/time';
import { useEnc } from './ctx';
import { NotBuilt, type Loadable } from './States';
import { TierBadge } from './TierBadge';

export function Glance({ glance, closure, bubbles, onQuestions }: {
  glance: Loadable<GlanceView>;
  closure: Loadable<ClosureView>;
  bubbles: Loadable<BubbleList>;
  flags: readonly Flag[];
  onQuestions: () => void;
}) {
  const { staffName, flagById } = useEnc();
  if (glance.kind === 'loading') return <section className="glance" aria-label="At a glance"><p className="note note-quiet">Loading…</p></section>;
  if (glance.kind === 'no_run') {
    return (
      <section className="glance glance-none" aria-label="At a glance">
        <p className="glance-headline">No check run yet</p>
        <p className="glance-detail">Choose a cutoff below and run checks to cross-read this record.</p>
      </section>
    );
  }
  if (glance.kind === 'not_built' || glance.kind === 'error') {
    return (
      <section className="glance" aria-label="At a glance">
        {glance.kind === 'not_built' ? <NotBuilt what="The glance strip" /> : <p className="note note-problem">The glance strip could not be loaded (server code {glance.code}).</p>}
        {closure.kind === 'ok' && (
          <p className="glance-detail">Closure view: {CLOSURE_STATUS[closure.data.status].headline.toLowerCase()} ({closure.data.tier1_blockers.length} Tier 1 blocking).</p>
        )}
      </section>
    );
  }
  const g = glance.data;
  const status = CLOSURE_STATUS[g.closure_status];
  const owners = g.tier1_owner_ids.map(staffName).join(', ');
  const byId = new Map(bubbles.kind === 'ok' ? bubbles.data.bubbles.map((b) => [b.bubble_id, b] as const) : []);
  const decisions = closure.kind === 'ok' ? [...closure.data.decisions].reverse().slice(0, 3) : [];
  return (
    <section className={`glance glance-${g.closure_status}`} aria-label="At a glance">
      <p className="glance-headline">
        {status.headline}
        {g.open_tier1 > 0 ? `: ${g.open_tier1} Tier 1 item${g.open_tier1 > 1 ? 's' : ''} with ${owners}` : ''}
      </p>
      <p className="glance-detail">{status.detail} Sources checked up to {sgtDateTime(g.cutoff)}.</p>
      <ul className="glance-counts" aria-label="Open items by tier">
        <li><TierBadge tier={1} /> <strong>{g.open_tier1}</strong> open</li>
        <li><TierBadge tier={2} /> <strong>{g.open_tier2}</strong> open</li>
        <li><TierBadge tier={3} /> <strong>{g.open_tier3}</strong> open</li>
      </ul>
      {g.top_bubble_ids.length > 0 && (
        <div className="glance-questions">
          <h2>Top questions</h2>
          <ol>
            {g.top_bubble_ids.map((id, i) => {
              const b = byId.get(id);
              const st = g.top_bubble_statuses[i];
              return (
                <li key={id}>
                  <button type="button" className="link" onClick={onQuestions}>{b ? b.question : 'Question'}</button>
                  {st ? <span className="glance-q-status"> {BUBBLE_STATUS[st]}</span> : null}
                </li>
              );
            })}
          </ol>
        </div>
      )}
      {decisions.length > 0 && (
        <div className="glance-decisions">
          <h2>Latest decisions</h2>
          <ul>
            {decisions.map((d) => (
              <li key={d.decision_id}>
                {staffName(d.actor_staff_id)} {humanize(d.action).toLowerCase()}: {flagById(d.flag_id)?.title ?? 'a flag'}, {sgtTime(d.at)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
