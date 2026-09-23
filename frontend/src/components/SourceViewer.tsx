import { useEffect, useMemo, useRef, useState } from 'react';
import { api, routePath } from '../api/client';
import type { DocumentTokenView, Evidence, SourceText, SourceView } from '../api/types';
import { EXTRACTION, SOURCE_TYPE } from '../lib/labels';
import { checkSpan, segments } from '../lib/offsets';
import { sgtDateTime } from '../lib/time';
import { useEnc, type SourceTarget } from './ctx';
import { Loaded, toLoadable, type Loadable } from './States';

function VersionPane({ version, evidence, label }: { version: SourceView; evidence: readonly Evidence[]; label: string }) {
  const { view } = useEnc();
  const [text, setText] = useState<Loadable<SourceText>>({ kind: 'loading' });
  const firstMark = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let live = true;
    setText({ kind: 'loading' });
    void api<SourceText>('GET', 'SOURCE_TEXT', { encounter_id: view.encounter.encounter_id, source_version_id: version.note_version_id })
      .then((r) => { if (live) setText(toLoadable(r)); });
    return () => { live = false; };
  }, [view.encounter.encounter_id, version.note_version_id]);

  const marked = useMemo(() => {
    if (text.kind !== 'ok') return null;
    const body = text.data.text;
    const mine = evidence.filter((e) => e.note_version_id === version.note_version_id && e.role_in_flag !== 'extraction_gap' && e.quote !== '');
    const ranges: { start: number; end: number }[] = [];
    let unmatched = 0;
    for (const e of mine) {
      const c = checkSpan(body, e.start, e.end, e.quote);
      if (c.ok) ranges.push({ start: c.start, end: c.end });
      else unmatched += 1;
    }
    return { segs: segments(body, ranges), matched: ranges.length, unmatched, empty: body.length === 0 };
  }, [text, evidence, version.note_version_id]);

  useEffect(() => {
    firstMark.current?.scrollIntoView?.({ block: 'center' });
  }, [marked]);

  return (
    <div className="version-pane">
      <h3 className="version-label">{label}</h3>
      <Loaded value={text} what="Source text" noRun={
        <p className="note note-problem" role="alert">
          This source version is no longer available (the server answered 404). The citation still points to it; no other text is shown in its place.
        </p>
      }>
        {() => marked && (
          <>
            {marked.unmatched > 0 && (
              <p className="note note-problem" role="alert">
                {marked.unmatched} cited span{marked.unmatched > 1 ? 's do' : ' does'} not match this text and {marked.unmatched > 1 ? 'are' : 'is'} not highlighted.
              </p>
            )}
            {marked.empty ? (
              <p className="note note-problem">No text could be extracted from this document. Review the original.</p>
            ) : (
              <pre className="source-text record-text" data-testid="source-text">
                {marked.segs.map((s, i) => s.mark
                  ? <mark key={i} ref={s.first ? (el) => { firstMark.current = el; } : undefined}>{s.text}</mark>
                  : <span key={i}>{s.text}</span>)}
              </pre>
            )}
          </>
        )}
      </Loaded>
    </div>
  );
}

export function SourceViewer({ target, onClose, asSheet }: { target: SourceTarget | null; onClose?: () => void; asSheet: boolean }) {
  const { view, source, newerVersion, staffName } = useEnc();
  const [docProblem, setDocProblem] = useState<string | null>(null);
  if (!target) {
    return <section className="viewer viewer-empty" aria-label="Source viewer"><p className="note note-quiet">Choose a source or a piece of evidence to read it here, with the cited words highlighted.</p></section>;
  }
  const cited = source(target.versionId);
  if (!cited) return <section className="viewer" aria-label="Source viewer"><p className="note note-problem">This source version is not in the workspace.</p></section>;
  const newer = newerVersion(target.versionId);
  const heading = `${cited.title}, ${staffName(cited.author_staff_id)}, ${sgtDateTime(cited.source_time)}`;

  const openPdf = async () => {
    setDocProblem(null);
    const r = await api<DocumentTokenView>('POST', 'DOCUMENT_TOKEN', { encounter_id: view.encounter.encounter_id, source_version_id: cited.note_version_id });
    if (!r.ok) {
      setDocProblem(r.status === 501 ? 'Opening the original is not available in this build.' : `The original could not be opened (server code ${r.errorCode}).`);
      return;
    }
    window.open(routePath('DOCUMENT', { document_token: r.data.document_token }), '_blank', 'noopener,noreferrer');
  };

  return (
    <section className={asSheet ? 'viewer viewer-sheet' : 'viewer'} aria-label="Source viewer" role={asSheet ? 'dialog' : undefined} aria-modal={asSheet || undefined}>
      <header className="viewer-head">
        <div>
          <h2>{heading}</h2>
          <p className="viewer-meta">
            {SOURCE_TYPE[cited.source_type]}; version {cited.version}, recorded {sgtDateTime(cited.version_time)}; {EXTRACTION[cited.extraction_status]}
          </p>
        </div>
        {onClose && <button type="button" className="btn btn-quiet" onClick={onClose}>Close</button>}
      </header>
      {cited.source_type === 'pdf' && (
        <div className={cited.extraction_note ? 'note note-problem' : 'note note-quiet'} role="note">
          PDF, {cited.page_count} page{cited.page_count === 1 ? '' : 's'}. {EXTRACTION[cited.extraction_status]}.
          {cited.extraction_note ? ` ${cited.extraction_note}.` : ''}{' '}
          <button type="button" className="link" onClick={() => void openPdf()}>Open the original PDF</button>
          {docProblem && <span> {docProblem}</span>}
        </div>
      )}
      {newer ? (
        <>
          <p className="note note-change">Source changed since it was cited: version {newer.version} was recorded {sgtDateTime(newer.version_time)}. Both versions are shown; the flag keeps citing the version it was raised on.</p>
          <div className="viewer-compare">
            <VersionPane version={cited} evidence={target.evidence} label={`Cited: version ${cited.version}`} />
            <VersionPane version={newer} evidence={[]} label={`Current: version ${newer.version}`} />
          </div>
        </>
      ) : (
        <VersionPane version={cited} evidence={target.evidence} label={`Version ${cited.version}`} />
      )}
    </section>
  );
}
