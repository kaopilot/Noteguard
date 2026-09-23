import type { ReactNode } from 'react';
import type { ApiResult } from '../api/client';

/** Every server-backed view is one of these; `not_built` is a 501 and never shows a stand-in value. */
export type Loadable<T> =
  | { kind: 'loading' }
  | { kind: 'ok'; data: T }
  | { kind: 'no_run' }
  | { kind: 'not_built' }
  | { kind: 'error'; code: string; status: number };

export function toLoadable<T>(r: ApiResult<T>): Loadable<T> {
  if (r.ok) return { kind: 'ok', data: r.data };
  if (r.status === 501) return { kind: 'not_built' };
  if (r.status === 404) return { kind: 'no_run' };
  return { kind: 'error', code: r.errorCode, status: r.status };
}

export function NotBuilt({ what }: { what: string }) {
  return (
    <div className="note note-notbuilt" role="status">
      <strong>{what} is not available in this build.</strong>{' '}
      The server answered 501 (not implemented), so nothing is shown in its place.
    </div>
  );
}

export function Loaded<T>({ value, what, children, noRun }: {
  value: Loadable<T>;
  what: string;
  children: (data: T) => ReactNode;
  noRun?: ReactNode;
}) {
  switch (value.kind) {
    case 'loading':
      return <p className="note note-quiet" role="status">Loading {what.toLowerCase()}…</p>;
    case 'not_built':
      return <NotBuilt what={what} />;
    case 'no_run':
      return <>{noRun ?? <p className="note note-quiet">{what}: no check run yet. Run checks to see it.</p>}</>;
    case 'error':
      return <p className="note note-problem" role="alert">{what} could not be loaded (server code {value.code}).</p>;
    default:
      return <>{children(value.data)}</>;
  }
}
