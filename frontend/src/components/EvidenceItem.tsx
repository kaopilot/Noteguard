import type { Evidence } from '../api/types';
import { EVIDENCE_ROLE } from '../lib/labels';
import { sgtTime } from '../lib/time';
import { RECORD_FIELD } from './cite';
import { useEnc } from './ctx';

/** One evidence anchor: a quoted span, an unread page, or a care-team record field. */
export function EvidenceItem({ ev, all }: { ev: Evidence; all: readonly Evidence[] }) {
  const { source, staffName, openSource } = useEnc();
  const role = EVIDENCE_ROLE[ev.role_in_flag];

  if (ev.record_field) {
    return (
      <li className="ev ev-record">
        <span className="ev-role">{role}</span>
        <span className="ev-body">Care-team record: {RECORD_FIELD[ev.record_field]}</span>
      </li>
    );
  }
  const src = source(ev.note_version_id);
  const origin = src
    ? `${src.title}, ${staffName(src.author_staff_id)}, ${sgtTime(src.source_time)}${src.version > 1 ? `, version ${src.version}` : ''}`
    : 'Source version not in this workspace';
  const versionId = ev.note_version_id ?? '';
  const open = () => openSource({ versionId, evidence: all, heading: origin });

  if (ev.role_in_flag === 'extraction_gap') {
    const what = src?.extraction_status === 'no_text_layer' ? 'has no text layer' : 'could not be fully read';
    return (
      <li className="ev ev-gap">
        <span className="ev-role">{role}</span>
        <span className="ev-body">
          Page {ev.page ?? '?'} {what}: {origin}
          {src?.extraction_note ? <span className="ev-note"> ({src.extraction_note})</span> : null}
        </span>
        {src ? <button type="button" className="link" onClick={open}>Show source</button> : null}
      </li>
    );
  }
  return (
    <li className="ev">
      <span className="ev-role">{role}</span>
      <blockquote className="ev-quote record-text">{ev.quote}</blockquote>
      <span className="ev-origin">{origin}{ev.page ? `, page ${ev.page}` : ''}</span>
      {src ? <button type="button" className="link" onClick={open}>Show in source</button> : null}
    </li>
  );
}
