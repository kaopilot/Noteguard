import type { Evidence, SourceView } from '../api/types';
import { sgtTime } from '../lib/time';

export const RECORD_FIELD: Record<NonNullable<Evidence['record_field']>, string> = {
  'encounter.responsible_clinician_id': 'no responsible clinician recorded',
};

/** Plain-text citation for summaries and copy: a quoted span, an unread page, or a record field. */
export function citeText(ev: Evidence, src: SourceView | undefined, staffName: (id: string) => string): string {
  if (ev.record_field) return `Care-team record: ${RECORD_FIELD[ev.record_field]}`;
  const where = src ? `${src.title}, ${staffName(src.author_staff_id)}, ${sgtTime(src.source_time)}${src.version > 1 ? `, version ${src.version}` : ''}` : 'Unknown source version';
  if (ev.role_in_flag === 'extraction_gap') return `${where}: page ${ev.page ?? '?'}, no text extracted`;
  return `${where}${ev.page ? `, page ${ev.page}` : ''}: \u201c${ev.quote}\u201d`;
}
