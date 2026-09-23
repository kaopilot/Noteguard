import { useId, useState } from 'react';
import type { CheckRunView } from '../api/types';
import { humanize } from '../lib/labels';
import { sgtDateTime, sgtInputToUtc, toSgtInputSecondsCeil } from '../lib/time';
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
  // Default: everything recorded so far. Compare as instants (ISO strings with and without fractional
  // seconds do not sort correctly as text) and round up to the second (see toSgtInputSecondsCeil).
  const latest = view.sources.reduce((m, s) => (Date.parse(s.version_time) > Date.parse(m) ? s.version_time : m), view.encounter.started_at);
  const [value, setValue] = useState(toSgtInputSecondsCeil(latest));
  const [invalid, setInvalid] = useState(false);
  const [open, setOpen] = useState(false);
  const submit = () => {
    const utc = sgtInputToUtc(value);
    setInvalid(utc === null);
    if (utc) {
      setOpen(false);
      onRun(utc);
    }
  };
  const form = (
    <form className="run-form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <label htmlFor={inputId} className="run-label">Check sources up to (Singapore time)</label>
      <div className="run-row">
        <input id={inputId} type="datetime-local" step={1} value={value} onChange={(e) => setValue(e.target.value)} required />
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Running…' : 'Run checks'}</button>
      </div>
      {invalid && <p className="note note-problem" role="alert">Enter a date and time.</p>}
      {problem && <p className="note note-problem" role="alert">{problem}</p>}
    </form>
  );
  if (run.kind !== 'ok') return <section className="run" aria-label="Run checks">{form}</section>;
  return (
    <details className="run" open={open || problem !== null} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <span className="run-last">
          Checked up to {sgtDateTime(run.data.run.source_cutoff)}: ruleset {run.data.run.ruleset_version},
          registry {run.data.run.registry_version}; {humanize(run.data.run.outcome).toLowerCase()}.
        </span>{' '}
        <span className="run-again">Run checks again</span>
      </summary>
      {form}
    </details>
  );
}
