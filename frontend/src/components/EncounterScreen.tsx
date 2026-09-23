import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { api, type ApiResult } from '../api/client';
import type {
  BubbleList, CheckRunView, ClosureView, EncounterView, Flag, FlagDetail, GlanceView, SessionView, Summary as SummaryT,
} from '../api/types';
import { ROSTER } from '../lib/roster';
import { Bubbles } from './Bubbles';
import { Closure } from './Closure';
import { EncounterCtx, type EncounterCtxValue, type SourceTarget } from './ctx';
import { DecisionSheet } from './DecisionSheet';
import { FlagList } from './FlagList';
import { Glance } from './Glance';
import { RunControl } from './RunControl';
import { SourceViewer } from './SourceViewer';
import { Loaded, toLoadable, type Loadable } from './States';
import { Summary } from './Summary';
import { Timeline } from './Timeline';

type Tab = 'review' | 'questions' | 'closure' | 'summary';
const TABS: { id: Tab; label: string }[] = [
  { id: 'review', label: 'Review' },
  { id: 'questions', label: 'Questions' },
  { id: 'closure', label: 'Closure' },
  { id: 'summary', label: 'Summary' },
];
const WIDE = '(min-width: 1100px)';

function useWide(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = typeof window.matchMedia === 'function' ? window.matchMedia(WIDE) : null;
      m?.addEventListener('change', cb);
      return () => m?.removeEventListener('change', cb);
    },
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(WIDE).matches : false),
  );
}

export function EncounterScreen({ me, encounterId, onBack, onSessionProblem }: {
  me: SessionView;
  encounterId: string;
  onBack: () => void;
  onSessionProblem: (code: string) => void;
}) {
  const wide = useWide();
  const [view, setView] = useState<Loadable<EncounterView>>({ kind: 'loading' });
  const [run, setRun] = useState<Loadable<CheckRunView>>({ kind: 'loading' });
  const [flags, setFlags] = useState<Loadable<Flag[]>>({ kind: 'loading' });
  const [bubbles, setBubbles] = useState<Loadable<BubbleList>>({ kind: 'loading' });
  const [glance, setGlance] = useState<Loadable<GlanceView>>({ kind: 'loading' });
  const [closure, setClosure] = useState<Loadable<ClosureView>>({ kind: 'loading' });
  const [summary, setSummary] = useState<Loadable<SummaryT>>({ kind: 'loading' });
  const [tab, setTab] = useState<Tab>('review');
  const [pane, setPane] = useState<'flags' | 'record'>('flags');
  const [target, setTarget] = useState<SourceTarget | null>(null);
  const [deciding, setDeciding] = useState<Flag | null>(null);
  const [focusFlag, setFocusFlag] = useState<string | null>(null);
  const [runBusy, setRunBusy] = useState(false);
  const [runProblem, setRunProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const p = useMemo(() => ({ encounter_id: encounterId }), [encounterId]);
  const watch = useCallback(<T,>(r: ApiResult<T>): Loadable<T> => {
    if (!r.ok && (r.errorCode === 'unauthenticated' || r.errorCode === 'workspace_expired' || r.errorCode === 'workspace_required')) {
      onSessionProblem(r.errorCode);
    }
    return toLoadable(r);
  }, [onSessionProblem]);

  const loadDerived = useCallback(async () => {
    const [r, f, b, g, c, s] = await Promise.all([
      api<CheckRunView>('GET', 'CHECK_RUN_LATEST', p),
      api<Flag[]>('GET', 'FLAGS', p),
      api<BubbleList>('GET', 'BUBBLES', p),
      api<GlanceView>('GET', 'GLANCE', p),
      api<ClosureView>('GET', 'CLOSURE', p),
      api<SummaryT>('GET', 'SUMMARY', p),
    ]);
    setRun(watch(r)); setFlags(watch(f)); setBubbles(watch(b)); setGlance(watch(g)); setClosure(watch(c)); setSummary(watch(s));
  }, [p, watch]);

  useEffect(() => {
    void (async () => {
      const v = watch(await api<EncounterView>('GET', 'ENCOUNTER', p));
      setView(v);
      if (v.kind === 'ok') await loadDerived();
    })();
  }, [p, watch, loadDerived]);

  const runChecks = async (cutoff: string) => {
    setRunBusy(true);
    setRunProblem(null);
    const r = await api<CheckRunView>('POST', 'CHECK_RUNS', p, { cutoff });
    setRunBusy(false);
    if (!r.ok) {
      watch(r);
      setRunProblem(r.status === 501 ? 'Running checks is not available in this build.' : `Checks did not run (server code ${r.errorCode}).`);
      return;
    }
    setNotice(`Checks ran over sources up to the chosen cutoff: ${r.data.flags.length} current flags.`);
    await loadDerived();
  };

  const flagList = flags.kind === 'ok' ? flags.data : [];
  const ctx: EncounterCtxValue | null = useMemo(() => {
    if (view.kind !== 'ok') return null;
    const v = view.data;
    const staff = new Map([...ROSTER, ...v.staff].map((s) => [s.staff_id, s.display_name] as const));
    const byVersion = new Map(v.sources.map((s) => [s.note_version_id, s] as const));
    return {
      me,
      view: v,
      staffName: (id) => (id ? staff.get(id) ?? 'Unknown staff member' : 'Nobody'),
      source: (id) => (id ? byVersion.get(id) : undefined),
      newerVersion: (id) => {
        const cur = byVersion.get(id);
        if (!cur) return undefined;
        const latest = v.sources.filter((s) => s.source_id === cur.source_id).sort((a, b) => b.version - a.version)[0];
        return latest && latest.note_version_id !== id ? latest : undefined;
      },
      openSource: (t) => { setTarget(t); if (!wide) setPane('record'); },
      openFlag: (id) => { setTab('review'); setPane('flags'); setFocusFlag(id); },
      flagById: (id) => flagList.find((f) => f.flag_id === id),
    };
  }, [view, me, wide, flagList]);

  useEffect(() => {
    if (focusFlag) document.getElementById(`card-${focusFlag}`)?.scrollIntoView?.({ block: 'start' });
  }, [focusFlag, tab]);

  if (view.kind !== 'ok' || !ctx) {
    return (
      <main className="screen">
        <button type="button" className="link" onClick={onBack}>All encounters</button>
        {view.kind === 'no_run'
          ? <p className="note note-problem" role="alert">This encounter is not available to you. Access follows care-team membership.</p>
          : <Loaded value={view} what="Encounter">{() => null}</Loaded>}
      </main>
    );
  }
  const v = view.data;
  const onDecided = (d: FlagDetail) => {
    setDeciding(null);
    setNotice(`Recorded: ${d.flag.title} is now ${d.flag.state} (revision ${d.flag.revision}).`);
    void loadDerived();
  };
  const flagsPanel = (
    <Loaded value={flags} what="Flags" noRun={<p className="note note-quiet">No flags yet: run checks first.</p>}>
      {(list) => <FlagList flags={list} closure={closure.kind === 'ok' ? closure.data : null} focusFlagId={focusFlag} onDecide={setDeciding} />}
    </Loaded>
  );
  const sourceOverlay = !wide && target !== null;

  return (
    <EncounterCtx.Provider value={ctx}>
      <main className="screen">
        <div className="enc-head">
          <button type="button" className="link" onClick={onBack}>All encounters</button>
          <h1>{v.encounter.encounter_ref}: {v.patient_label}</h1>
          <p className="enc-sub">{v.encounter.setting}; responsible clinician {v.encounter.responsible_clinician_id ? ctx.staffName(v.encounter.responsible_clinician_id) : 'not recorded'}</p>
        </div>
        <Glance glance={glance} closure={closure} bubbles={bubbles} flags={flagList} onQuestions={() => setTab('questions')} />
        <RunControl run={run} busy={runBusy} problem={runProblem} onRun={(c) => void runChecks(c)} />
        {notice && <p className="note note-change" role="status">{notice}</p>}
        <nav className="tabs" aria-label="Encounter views">
          {TABS.map((t) => (
            <button key={t.id} type="button" className="tab" aria-current={tab === t.id ? 'page' : undefined} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
        {tab === 'review' && (wide ? (
          <div className="three-pane">
            <Timeline run={run} flags={flagList} />
            <SourceViewer target={target} asSheet={false} />
            <div className="pane-flags">{flagsPanel}</div>
          </div>
        ) : (
          <div className="one-pane">
            <div className="segmented" role="group" aria-label="Show">
              <button type="button" aria-pressed={pane === 'flags'} onClick={() => setPane('flags')}>Flags</button>
              <button type="button" aria-pressed={pane === 'record'} onClick={() => setPane('record')}>Record</button>
            </div>
            {pane === 'flags' ? flagsPanel : <Timeline run={run} flags={flagList} />}
          </div>
        ))}
        {tab === 'questions' && <Bubbles bubbles={bubbles} />}
        {tab === 'closure' && (
          <Closure closure={closure} onReviewTier3={() => { setTab('review'); setPane('flags'); setTimeout(() => document.getElementById('tier-group-3')?.scrollIntoView?.(), 0); }} />
        )}
        {tab === 'summary' && <Summary summary={summary} />}
      </main>
      {sourceOverlay && <div className="sheet-backdrop"><SourceViewer target={target} asSheet onClose={() => setTarget(null)} /></div>}
      {deciding && (
        <DecisionSheet flag={deciding} otherFlags={flagList} onClose={() => setDeciding(null)} onDecided={onDecided} onStale={() => void loadDerived()} />
      )}
    </EncounterCtx.Provider>
  );
}
