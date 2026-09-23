import type { BubbleList } from '../api/types';
import { BUBBLE_STATUS, humanize, subjectName } from '../lib/labels';
import { sgtDateTime } from '../lib/time';
import { useEnc } from './ctx';
import { EvidenceItem } from './EvidenceItem';
import { Loaded, type Loadable } from './States';

export function Bubbles({ bubbles }: { bubbles: Loadable<BubbleList> }) {
  const { openFlag } = useEnc();
  return (
    <section className="bubbles" aria-label="Questions">
      <h2 className="pane-title">Questions the record should answer</h2>
      <Loaded value={bubbles} what="Questions">
        {(list) => (
          <>
            <p className="note note-quiet">
              Answered by the deterministic checker from the supplied sources up to {sgtDateTime(list.cutoff)}.
              {list.ai_status === 'disabled' ? 'AI drafting disabled.' : `AI drafting: ${humanize(list.ai_status).toLowerCase()}.`}
            </p>
            {list.bubbles.map((b) => (
              <article key={b.bubble_id} className={`bubble bubble-${b.status}`}>
                <h3>{b.question}</h3>
                <p className="bubble-status"><span className="bubble-mark" aria-hidden="true" />{BUBBLE_STATUS[b.status]}</p>
                <p className="bubble-note">{b.uncertainty_note}</p>
                {b.absence && (
                  <p className="bubble-scope">
                    Search scope: {b.absence.terms_searched.map(subjectName).join(', ')} across {b.absence.sources_searched.length} source
                    versions up to {sgtDateTime(b.absence.cutoff)} (registry {b.absence.registry_version}).
                  </p>
                )}
                <ul className="ev-list">{b.evidence.map((ev, i) => <EvidenceItem key={i} ev={ev} all={b.evidence} />)}</ul>
                {b.flag_id && <button type="button" className="link" onClick={() => openFlag(b.flag_id ?? '')}>Open the related flag</button>}
              </article>
            ))}
          </>
        )}
      </Loaded>
    </section>
  );
}
