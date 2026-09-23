import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { api, newIdempotencyKey, type ErrorCode } from '../api/client';
import { disciplineValues } from '../api/schema.gen';
import type { AddTextSourceRequest, Discipline, SourceView } from '../api/types';
import { DISCIPLINE } from '../lib/labels';
import { sgtDateTime, sgtInputToUtc, toSgtInput } from '../lib/time';
import { useEnc } from './ctx';

type Kind = 'text' | 'pdf';
// identifier_namespace is deliberately never sent: the server default applies to new sources, and a
// new version must keep its source's own namespace (sending a different one is refused).
type TextBody = Omit<AddTextSourceRequest, 'identifier_namespace'>;

const ERROR_TEXT: Partial<Record<ErrorCode, string>> = {
  validation_failed: 'The server refused these details. The author must be on the care team, and a new version must keep the original title, author, discipline and time.',
  not_found: 'That source is no longer in this workspace. Nothing was added.',
  forbidden_role: 'Your role cannot add sources to this encounter.',
  idempotency_conflict: 'An earlier submission with the same key had different content. Nothing was added; submit again.',
  pdf_too_large: 'This PDF is larger than the server accepts. Nothing was added.',
  pdf_not_a_pdf: 'This file is not a PDF. Nothing was added.',
  pdf_too_many_pages: 'This PDF has more pages than the server accepts. Nothing was added.',
  rate_limited: 'Too many requests. Wait a moment, then submit again.',
  not_implemented: 'Adding sources is not available in this build.',
  workspace_expired: 'This workspace has expired. Start a fresh case.',
};

/** Add a pasted note or a PDF, as a new source or a new version of an existing one. The note text
 * and file stay in this component's memory until sent; nothing is logged or stored in the browser. */
export function AddSource({ onClose, onAdded }: {
  onClose: () => void;
  /** created=false: identical content was already recorded (idempotent replay). retained: PDF kept
   * although extraction did not finish. */
  onAdded: (v: SourceView | null, outcome: 'created' | 'replay' | 'retained') => void;
}) {
  const { me, view } = useEnc();
  const titleId = useId();
  const fid = useId();
  const panel = useRef<HTMLDivElement>(null);
  const members = useMemo(
    () => view.staff.filter((s) => view.memberships.some((m) => m.staff_id === s.staff_id)),
    [view.staff, view.memberships],
  );
  const logical = useMemo(() => {
    const latest = new Map<string, SourceView>();
    for (const s of view.sources) if ((latest.get(s.source_id)?.version ?? 0) < s.version) latest.set(s.source_id, s);
    return [...latest.values()];
  }, [view.sources]);

  const [kind, setKind] = useState<Kind>('text');
  const [amendOf, setAmendOf] = useState('');
  const initialAuthor = members.find((s) => s.staff_id === me.staff_id) ?? members[0];
  const [author, setAuthor] = useState(initialAuthor?.staff_id ?? '');
  const [discipline, setDiscipline] = useState<Discipline>(initialAuthor?.discipline ?? 'other');
  const [title, setTitle] = useState('');
  const [when, setWhen] = useState(() => toSgtInput(new Date().toISOString()));
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // Any change to what would be submitted is a new intended submission, so it gets a new key.
  useEffect(() => { setKey(newIdempotencyKey()); }, [kind, amendOf, author, discipline, title, when, text, file]);
  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const wantedType = kind === 'text' ? 'pasted_text' : 'pdf';
  const amendable = logical.filter((s) => s.source_type === wantedType);
  const amending = amendable.find((s) => s.source_id === amendOf) ?? null;

  const chooseAmend = (id: string) => {
    setAmendOf(id);
    const s = logical.find((x) => x.source_id === id);
    if (s) {
      setTitle(s.title);
      setAuthor(s.author_staff_id);
      setDiscipline(s.discipline);
      setWhen(toSgtInput(s.source_time));
    }
  };
  const chooseKind = (k: Kind) => { setKind(k); setAmendOf(''); setProblem(null); };
  const chooseAuthor = (id: string) => {
    setAuthor(id);
    const s = members.find((x) => x.staff_id === id);
    if (s) setDiscipline(s.discipline);
  };

  const sourceTime = sgtInputToUtc(when);
  const ready = !busy && title.trim() !== '' && author !== '' && sourceTime !== null && (kind === 'text' ? text.trim() !== '' : file !== null);

  const submit = async () => {
    if (!ready || sourceTime === null) return;
    setBusy(true);
    setProblem(null);
    const params = { encounter_id: view.encounter.encounter_id };
    let r;
    if (kind === 'text') {
      const body: TextBody = {
        title: title.trim(), discipline, author_staff_id: author, source_time: sourceTime, text,
        source_id: amending ? amending.source_id : null, external_id: null, idempotency_key: key,
      };
      r = await api<SourceView>('POST', 'SOURCES', params, body);
    } else {
      const form = new FormData();
      form.append('file', file as File);
      form.append('title', title.trim());
      form.append('discipline', discipline);
      form.append('author_staff_id', author);
      form.append('source_time', sourceTime);
      form.append('idempotency_key', key);
      if (amending) form.append('source_id', amending.source_id);
      r = await api<SourceView>('POST', 'SOURCES_PDF', params, form);
    }
    setBusy(false);
    if (r.ok) {
      onAdded(r.data, r.status === 201 ? 'created' : 'replay');
      return;
    }
    if (r.errorCode === 'pdf_extraction_timeout') {
      onAdded(null, 'retained');
      return;
    }
    if (r.errorCode === 'idempotency_conflict') setKey(newIdempotencyKey());
    setProblem(r.errorCode === 'network'
      ? 'No connection, so nothing was confirmed. Submitting again is safe: it cannot add the note twice.'
      : ERROR_TEXT[r.errorCode as ErrorCode] ?? `The server did not add this source (code ${r.errorCode}).`);
  };

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={panel} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" aria-hidden="true" />
        <div className="sheet-head">
          <h2 id={titleId}>Add a source</h2>
          <button type="button" className="btn btn-quiet" onClick={onClose}>Close</button>
        </div>
        <p className="sheet-sub">
          Sources are never overwritten: a correction is added as a new version beside the original. Check runs include a source
          only if their cutoff is at or after the moment it is recorded here.
        </p>
        <form className="decision-form" aria-labelledby={titleId} onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <fieldset>
            <legend>What are you adding?</legend>
            <label className="choice">
              <input type="radio" name="source-kind" checked={kind === 'text'} onChange={() => chooseKind('text')} />
              <span><strong>Paste a note</strong><small>Typed text, stored exactly as pasted.</small></span>
            </label>
            <label className="choice">
              <input type="radio" name="source-kind" checked={kind === 'pdf'} onChange={() => chooseKind('pdf')} />
              <span><strong>Upload a PDF</strong><small>Scanned pages without a text layer are kept and labelled, never read as complete.</small></span>
            </label>
          </fieldset>
          <div className="field">
            <label htmlFor={`${fid}-amend`}>New source or new version</label>
            <select id={`${fid}-amend`} aria-describedby={amending ? `${fid}-amend-hint` : undefined} value={amendOf} onChange={(e) => (e.target.value ? chooseAmend(e.target.value) : setAmendOf(''))}>
              <option value="">A new source</option>
              {amendable.map((s) => (
                <option key={s.source_id} value={s.source_id}>
                  New version of: {s.title} ({sgtDateTime(s.source_time)}, now version {s.version})
                </option>
              ))}
            </select>
            {amending && <small id={`${fid}-amend-hint`}>Title, author, discipline and time stay as recorded on the original.</small>}
          </div>
          <label className="field">
            <span>Title</span>
            <input value={title} maxLength={200} disabled={amending !== null} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="field">
            <span>Author (accountable care-team member)</span>
            <select value={author} disabled={amending !== null} onChange={(e) => chooseAuthor(e.target.value)}>
              {members.map((s) => <option key={s.staff_id} value={s.staff_id}>{s.display_name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Discipline</span>
            <select value={discipline} disabled={amending !== null} onChange={(e) => setDiscipline(e.target.value as Discipline)}>
              {disciplineValues.map((d) => <option key={d} value={d}>{DISCIPLINE[d]}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Clinical time of the note (Singapore time)</span>
            <input type="datetime-local" value={when} disabled={amending !== null} onChange={(e) => setWhen(e.target.value)} />
          </label>
          {kind === 'text' ? (
            <div className="field">
              <label htmlFor={`${fid}-text`}>Note text</label>
              <textarea id={`${fid}-text`} aria-describedby={`${fid}-text-hint`} className="record-text" rows={8} value={text} maxLength={200000}
                onChange={(e) => setText(e.target.value)} />
              <small id={`${fid}-text-hint`}>Held in this page’s memory until sent. Not stored on this device.</small>
            </div>
          ) : (
            <div className="field">
              <label htmlFor={`${fid}-file`}>PDF file</label>
              <input id={`${fid}-file`} aria-describedby={`${fid}-file-hint`} type="file" accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <small id={`${fid}-file-hint`}>The server checks the file type, size and page count.</small>
            </div>
          )}
          {problem && <p className="note note-problem" role="alert">{problem}</p>}
          <div className="sheet-actions">
            <button type="submit" className="btn btn-primary" disabled={!ready}>
              {busy ? 'Adding…' : amending ? `Add version ${amending.version + 1}` : 'Add source'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
