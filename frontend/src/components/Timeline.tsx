import type { ChangeView, CheckRunView, Evidence, Flag } from '../api/types';
import { CHANGE_KIND, DISCIPLINE, EXTRACTION, SOURCE_TYPE, subjectName } from '../lib/labels';
import { sgtTime } from '../lib/time';
import { useEnc } from './ctx';
import type { Loadable } from './States';

type Chip = { key: string; sign: string; text: string; evidence: Evidence[]; kind: string };
const CONTRADICTION_LENS: Flag['lens'] = 'contradiction';

function useChips(changes: readonly ChangeView[], flags: readonly Flag[]) {
  const { source, staffName } = useEnc();
  const who = (versionId: string | null | undefined) => {
    const s = source(versionId);
    return s ? `${sgtTime(s.source_time)} (${staffName(s.author_staff_id)})` : 'an earlier source';
  };
  return (versionId: string): Chip[] => {
    const out: Chip[] = [];
    const mine = changes.filter((c) => c.to_evidence?.note_version_id === versionId);
    const fresh = mine.filter((c) => c.kind === 'new');
    const freshKeys = [...new Set(fresh.map((c) => c.subject_key))];
    if (freshKeys.length > 0) {
      out.push({ key: 'new', kind: 'new', sign: CHANGE_KIND.new.sign, text: `${freshKeys.length} new: ${freshKeys.map(subjectName).join(', ')}`,
        evidence: fresh.flatMap((c) => (c.to_evidence ? [c.to_evidence] : [])) });
    }
    const linked = new Map<string, Chip>();
    for (const c of mine.filter((x) => x.kind !== 'new' && x.from_evidence)) {
      const k = `${c.kind}|${c.from_evidence?.note_version_id}`;
      const existing = linked.get(k);
      const name = subjectName(c.subject_key);
      if (existing) {
        if (!existing.text.includes(name)) existing.text = existing.text.replace(' from ', `, ${name} from `);
        if (c.to_evidence) existing.evidence.push(c.to_evidence);
      } else {
        linked.set(k, { key: k, kind: c.kind, sign: CHANGE_KIND[c.kind].sign,
          text: `${CHANGE_KIND[c.kind].label}: ${name} from ${who(c.from_evidence?.note_version_id)}`,
          evidence: c.to_evidence ? [c.to_evidence] : [] });
      }
    }
    out.push(...linked.values());
    for (const c of changes.filter((x) => x.to_evidence === null && x.from_evidence?.note_version_id === versionId)) {
      out.push({ key: `rm|${c.subject_key}`, kind: c.kind, sign: CHANGE_KIND[c.kind].sign, text: `${CHANGE_KIND[c.kind].label}: ${subjectName(c.subject_key)}`, evidence: [] });
    }
    for (const f of flags.filter((x) => x.lens === CONTRADICTION_LENS && x.evidence.some((e) => e.note_version_id === versionId))) {
      const others = [...new Set(f.evidence.map((e) => e.note_version_id).filter((v): v is string => !!v && v !== versionId))];
      if (others.length > 0) {
        out.push({ key: `x|${f.flag_id}`, kind: 'contradicts', sign: '!', text: `contradicts ${others.map(who).join(', ')} (${f.title.toLowerCase()})`,
          evidence: f.evidence.filter((e) => e.note_version_id === versionId) });
      }
    }
    return out;
  };
}

export function Timeline({ run, flags }: { run: Loadable<CheckRunView>; flags: readonly Flag[] }) {
  const { view, staffName, openSource, newerVersion } = useEnc();
  const changes = run.kind === 'ok' ? run.data.changes : [];
  const chipsFor = useChips(changes, flags);
  return (
    <section className="timeline" aria-label="Record timeline">
      <h2 className="pane-title">Record, oldest first</h2>
      {run.kind === 'ok' && changes.length === 0 && (
        <p className="note note-quiet">This check run reported no changes between sources, so no diff chips are shown.</p>
      )}
      {run.kind === 'no_run' && <p className="note note-quiet">Run checks to see what changed between sources.</p>}
      <ol className="tl">
        {view.sources.map((s) => {
          const newer = newerVersion(s.note_version_id);
          const chips = run.kind === 'ok' ? chipsFor(s.note_version_id) : [];
          const open = (evidence: readonly Evidence[] = []) => openSource({ versionId: s.note_version_id, evidence });
          return (
            <li key={s.note_version_id} className={`tl-row${newer ? ' tl-row-old' : ''}`}>
              <time className="tl-time" dateTime={s.source_time}>{sgtTime(s.source_time)}</time>
              <div className="tl-body">
                <button type="button" className="tl-title" onClick={() => open()}>{s.title}</button>
                <p className="tl-meta">
                  {staffName(s.author_staff_id)}, {DISCIPLINE[s.discipline]}; {SOURCE_TYPE[s.source_type]}; version {s.version}
                  {s.version > 1 ? `, recorded ${sgtTime(s.version_time)}` : ''}
                </p>
                <p className={s.extraction_note ? 'tl-extraction tl-extraction-gap' : 'tl-extraction'}>
                  {EXTRACTION[s.extraction_status]}{s.extraction_note ? `: ${s.extraction_note}` : ''}
                </p>
                {newer && <p className="tl-superseded">Amended: version {newer.version} recorded {sgtTime(newer.version_time)}</p>}
                {chips.length > 0 && (
                  <ul className="chips" aria-label="What changed in this source">
                    {chips.map((c) => (
                      <li key={c.key}>
                        <button type="button" className={`chip chip-${c.kind}`} onClick={() => open(c.evidence)}>
                          <span className="chip-sign" aria-hidden="true">{c.sign}</span> {c.text}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
