import { useState } from 'react';
import { summaryClaimTemplateValues } from '../api/schema.gen';
import type { Summary as SummaryT, SummaryClaim } from '../api/types';
import { CLOSURE_STATUS, DISCIPLINE, EXTRACTION, SOURCE_TYPE } from '../lib/labels';
import { sgtDateTime, sgtTime } from '../lib/time';
import { citeText } from './cite';
import { useEnc } from './ctx';
import { Loaded, type Loadable } from './States';

const SECTION: Record<SummaryClaim['template'], string> = {
  open_priority: 'Open priorities',
  decision_record: 'Decisions',
  top_question: 'Top questions',
};

export function Summary({ summary }: { summary: Loadable<SummaryT> }) {
  const { view, source, staffName } = useEnc();
  const [copied, setCopied] = useState<string | null>(null);

  const asText = (s: SummaryT): string => {
    const lines = [s.human_review_statement, ''];
    if (s.stale_after_source_change) lines.push('Stale: sources changed after cutoff.', '');
    lines.push(`Encounter ${s.encounter_ref}, ${view.patient_label}, ${view.encounter.setting}`);
    lines.push(`Sources up to ${sgtDateTime(s.cutoff)}; generated ${sgtDateTime(s.generated_at)}; ruleset ${s.ruleset_version}, registry ${s.registry_version}`);
    lines.push(`Closure: ${CLOSURE_STATUS[s.closure_status].headline}`, '', 'Sources:');
    for (const t of s.timeline) lines.push(`- ${sgtTime(t.source_time)} ${t.title}, ${staffName(t.author_staff_id)}, ${DISCIPLINE[t.discipline]}, ${EXTRACTION[t.extraction_status]}`);
    for (const tpl of summaryClaimTemplateValues) {
      const claims = s.claims.filter((c) => c.template === tpl);
      if (claims.length === 0) continue;
      lines.push('', `${SECTION[tpl]}:`);
      for (const c of claims) {
        lines.push(`- ${c.text}`);
        for (const ev of c.evidence) lines.push(`    ${citeText(ev, source(ev.note_version_id), staffName)}`);
      }
    }
    return lines.join('\n');
  };

  const copy = async (s: SummaryT) => {
    try {
      await navigator.clipboard.writeText(asText(s));
      setCopied('Summary copied as plain text with its citations.');
    } catch {
      setCopied('Copying is not available in this browser. Use Print instead.');
    }
  };

  return (
    <section className="summary-wrap" aria-label="Summary">
      <Loaded value={summary} what="Summary">
        {(s) => (
          <article className="summary">
            <p className="summary-statement" role="note">{s.human_review_statement}</p>
            {s.stale_after_source_change && <p className="note note-problem" role="alert">Stale: sources changed after cutoff. Run checks again to regenerate this summary.</p>}
            <h2>Encounter {s.encounter_ref}: {view.patient_label}</h2>
            <dl className="summary-facts">
              <div><dt>Setting</dt><dd>{view.encounter.setting}</dd></div>
              <div><dt>Sources up to</dt><dd>{sgtDateTime(s.cutoff)}</dd></div>
              <div><dt>Generated</dt><dd>{sgtDateTime(s.generated_at)}</dd></div>
              <div><dt>Rules</dt><dd>Ruleset {s.ruleset_version}, registry {s.registry_version}</dd></div>
              <div><dt>Closure</dt><dd>{CLOSURE_STATUS[s.closure_status].headline}</dd></div>
            </dl>
            <h3>Sources</h3>
            <div className="table-wrap">
              <table className="summary-sources">
                <thead><tr><th scope="col">Time</th><th scope="col">Source</th><th scope="col">Author</th><th scope="col">Discipline</th><th scope="col">Type</th><th scope="col">Extraction</th></tr></thead>
                <tbody>
                  {s.timeline.map((t) => (
                    <tr key={t.note_version_id}>
                      <td>{sgtTime(t.source_time)}</td><td>{t.title}{t.version > 1 ? ` (v${t.version})` : ''}</td>
                      <td>{staffName(t.author_staff_id)}</td><td>{DISCIPLINE[t.discipline]}</td>
                      <td>{SOURCE_TYPE[t.source_type]}</td><td>{EXTRACTION[t.extraction_status]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {summaryClaimTemplateValues.map((tpl) => {
              const claims = s.claims.filter((c) => c.template === tpl);
              if (claims.length === 0) return null;
              return (
                <section key={tpl} className="summary-claims">
                  <h3>{SECTION[tpl]}</h3>
                  <ol>
                    {claims.map((c, i) => (
                      <li key={i}>
                        <p>{c.text}</p>
                        <ul className="cites">{c.evidence.map((ev, j) => <li key={j} className="record-text">{citeText(ev, source(ev.note_version_id), staffName)}</li>)}</ul>
                      </li>
                    ))}
                  </ol>
                </section>
              );
            })}
            <div className="summary-actions no-print">
              <button type="button" className="btn btn-primary" onClick={() => void copy(s)}>Copy summary</button>
              <button type="button" className="btn btn-quiet" onClick={() => window.print()}>Print</button>
              {copied && <p className="note note-quiet" role="status">{copied}</p>}
            </div>
          </article>
        )}
      </Loaded>
    </section>
  );
}
