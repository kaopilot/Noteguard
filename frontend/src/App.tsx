import { useCallback, useEffect, useState } from 'react';
import { api, setWorkspaceToken } from './api/client';
import type { EncounterListItem, SessionView, WorkspaceInfo } from './api/types';
import { Aggregate } from './components/Aggregate';
import { EncounterScreen } from './components/EncounterScreen';
import { humanize } from './lib/labels';
import { mayViewAggregate } from './lib/permissions';
import { ROSTER } from './lib/roster';

type Phase = 'boot' | 'login' | 'ready';
const OFFLINE = 'Offline — clinical content is not stored on this device.';

export function App() {
  const [phase, setPhase] = useState<Phase>('boot');
  const [me, setMe] = useState<SessionView | null>(null);
  const [ws, setWs] = useState<WorkspaceInfo | null>(null);
  const [encounters, setEncounters] = useState<EncounterListItem[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down); };
  }, []);

  const clearCase = () => {
    setWorkspaceToken(null);
    setWs(null);
    setEncounters(null);
    setOpen(null);
  };

  const startWorkspace = useCallback(async () => {
    setProblem(null);
    const w = await api<WorkspaceInfo>('POST', 'WORKSPACES');
    if (!w.ok) {
      if (w.errorCode === 'network') setOnline(false);
      setProblem(w.errorCode === 'unauthenticated' ? null : `A workspace could not be opened (server code ${w.errorCode}).`);
      if (w.errorCode === 'unauthenticated') setPhase('login');
      return;
    }
    setWorkspaceToken(w.data.workspace_token);
    setWs(w.data);
    const list = await api<EncounterListItem[]>('GET', 'ENCOUNTERS');
    setEncounters(list.ok ? list.data : []);
    if (!list.ok) setProblem(`Encounters could not be listed (server code ${list.errorCode}).`);
    setPhase('ready');
  }, []);

  useEffect(() => {
    void (async () => {
      const s = await api<SessionView>('GET', 'SESSION');
      if (s.ok) {
        setMe(s.data);
        await startWorkspace();
      } else {
        if (s.errorCode === 'network') setOnline(false);
        setPhase('login');
      }
    })();
  }, [startWorkspace]);

  const login = async (staffId: string) => {
    setProblem(null);
    const s = await api<SessionView>('POST', 'SESSION', undefined, { staff_id: staffId });
    if (!s.ok) {
      if (s.errorCode === 'network') setOnline(false);
      setProblem(`Sign-in did not succeed (server code ${s.errorCode}).`);
      return;
    }
    setMe(s.data);
    await startWorkspace();
  };

  const logout = async () => {
    await api('DELETE', 'SESSION');
    clearCase();
    setMe(null);
    setPhase('login');
  };

  const reset = async () => {
    setConfirmReset(false);
    const r = await api('DELETE', 'WORKSPACE_CURRENT');
    if (!r.ok && r.errorCode !== 'workspace_expired') {
      setProblem(r.status === 501 ? 'Reset is not available in this build.' : `Reset was refused (server code ${r.errorCode}).`);
      return;
    }
    clearCase();
    await startWorkspace();
  };

  const onSessionProblem = useCallback((code: string) => {
    clearCase();
    if (code === 'unauthenticated') {
      setMe(null);
      setPhase('login');
      setProblem('Your sign-in has ended. Sign in again.');
    } else {
      setProblem('This workspace has expired or is missing. A fresh case has been opened.');
      void startWorkspace();
    }
  }, [startWorkspace]);

  const canReset = ws !== null && ws.encounter_ids.length > 0;

  return (
    <div className="app">
      <header className="app-bar">
        <span className="brand"><span className="brand-mark" aria-hidden="true" />Noteguard</span>
        {me && (
          <div className="app-bar-right">
            <span className="who">{me.display_name}, {humanize(me.role).toLowerCase()}</span>
            {canReset && <button type="button" className="btn btn-quiet" onClick={() => setConfirmReset(true)}>Reset case</button>}
            <button type="button" className="btn btn-quiet" onClick={() => void logout()}>Sign out</button>
          </div>
        )}
      </header>
      {!online && <p className="banner-offline" role="status">{OFFLINE}</p>}
      {confirmReset && (
        <div className="confirm" role="alertdialog" aria-label="Reset case">
          <p>Reset discards this workspace: every decision and added source in it. The synthetic case starts again from the seed.</p>
          <button type="button" className="btn btn-primary" onClick={() => void reset()}>Reset now</button>
          <button type="button" className="btn btn-quiet" onClick={() => setConfirmReset(false)}>Keep working</button>
        </div>
      )}
      {problem && <p className="note note-problem app-problem" role="alert">{problem}</p>}
      {phase === 'boot' && <p className="note note-quiet screen">Starting…</p>}
      {phase === 'login' && (
        <main className="screen login">
          <h1>Sign in to the demonstrator</h1>
          <p>All people and records here are synthetic. Clinical content stays in this page’s memory and on the demonstrator server; a refresh or reset starts a fresh case.</p>
          <ul className="roster">
            {ROSTER.map((s) => (
              <li key={s.staff_id}>
                <button type="button" className="roster-btn" onClick={() => void login(s.staff_id)}>
                  <strong>{s.display_name}</strong><span>{humanize(s.role)}</span>
                </button>
              </li>
            ))}
          </ul>
        </main>
      )}
      {phase === 'ready' && me && !open && mayViewAggregate(me) && <Aggregate />}
      {phase === 'ready' && me && !open && !mayViewAggregate(me) && (
        <main className="screen">
          <h1>Encounters</h1>
          {encounters === null ? <p className="note note-quiet">Loading encounters…</p> : encounters.length === 0 ? (
            <p className="note note-quiet">No encounters are available to you. Access follows care-team membership, so ask the responsible clinician to add you.</p>
          ) : (
            <ul className="enc-list">
              {encounters.map((e) => (
                <li key={e.encounter_id}>
                  <button type="button" className="enc-btn" onClick={() => setOpen(e.encounter_id)}>
                    <strong>{e.encounter_ref}</strong>
                    <span>{e.patient_label}, {e.setting}</span>
                    <span>Responsible clinician: {e.responsible_clinician_id ? (ROSTER.find((s) => s.staff_id === e.responsible_clinician_id)?.display_name ?? 'on record') : 'not recorded'}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </main>
      )}
      {phase === 'ready' && me && open && ws && (
        <EncounterScreen key={`${ws.expires_at}-${open}`} me={me} encounterId={open} onBack={() => setOpen(null)} onSessionProblem={onSessionProblem} />
      )}
    </div>
  );
}
