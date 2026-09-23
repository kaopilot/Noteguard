import { useId, useState } from 'react';
import type { CheckRunView } from '../api/types';
import { humanize } from '../lib/labels';
import { sgtDateTime, sgtInputToUtc, toSgtInput } from '../lib/time';
import { useEnc } from './ctx';
import type { Loadable } from './States';

export function RunControl({ run, busy, problem, onRun }: {
  run: Loadable<CheckRunView>;
  busy: boolean;
  problem: string | null;
  onRun: (cutoffUtc: string) => void;
}) {
  const { view } = useEnc();
  const inputId = useId();
  const latest = view.sources.reduce((m, s) => (s.version_time > m ? s.version_time : m), view.encounter.started_at);
  const [value, setValue] = useState(toSgtInput(latest));
  const [invalid, setInvalid] = useState(false);
  const submit = () => {
    const utc = sgtInputToUtc(value);
    setInvalid(utc === null);
    if (utc) onRun(utc);
  };
  return (
    <form className="run" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <label htmlFor={inputId} className="run-label">Check sources up to (Singapore time)</label>
      <div className="run-row">
        <input id={inputId} type="datetime-local" value={value} onChange={(e) => setValue(e.target.value)} required />
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Running…' : 'Run checks'}</button>
      </div>
      {invalid && <p className="note note-problem" role="alert">Enter a date and time.</p>}
      {problem && <p className="note note-problem" role="alert">{problem}</p>}
      {run.kind === 'ok' && (
        <p className="run-last">
          Last run covers sources up to {sgtDateTime(run.data.run.source_cutoff)}: ruleset {run.data.run.ruleset_version},
          registry {run.data.run.registry_version}; {humanize(run.data.run.outcome).toLowerCase()}.
        </p>
      )}
    </form>
  );
}
