// The one HTTP client (B3). Routes, header names and error codes come from the generated
// contract data. The workspace token lives in this module's memory only (Section 6.3): never a
// cookie, never Web Storage, never IndexedDB. A page reload loses it by design (fresh case).
// Nothing here logs; response bodies can hold clinical text.
import { CONTRACT } from './contract-data.gen';

export type RouteKey = keyof typeof CONTRACT.routes;
export type ErrorCode = keyof typeof CONTRACT.error_http_status;
/** Client-side outcomes that are not server error codes. */
export type ClientFailure = 'network' | 'unrecognised_response';

let workspaceToken: string | null = null;

export function setWorkspaceToken(token: string | null): void {
  workspaceToken = token;
}

export function hasWorkspaceToken(): boolean {
  return workspaceToken !== null;
}

/** Fill a route template. Params are opaque IDs only (no clinical content in URLs, Section 10.2). */
export function routePath(route: RouteKey, params: Record<string, string> = {}): string {
  return CONTRACT.routes[route].replace(/\{(\w+)\}/g, (_m, name: string) => {
    const v = params[name];
    if (v === undefined) throw new Error(`route parameter missing: ${name}`);
    return encodeURIComponent(v);
  });
}

export type ApiOk<T> = { ok: true; status: number; data: T };
export type ApiErr = { ok: false; status: number; errorCode: ErrorCode | ClientFailure; body: unknown };
export type ApiResult<T> = ApiOk<T> | ApiErr;

function isErrorCode(code: string): code is ErrorCode {
  return Object.prototype.hasOwnProperty.call(CONTRACT.error_http_status, code);
}

export async function api<T>(
  method: 'GET' | 'POST' | 'DELETE',
  route: RouteKey,
  params?: Record<string, string>,
  body?: unknown,
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (workspaceToken !== null) headers[CONTRACT.workspace_header] = workspaceToken;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res: Response;
  try {
    res = await fetch(routePath(route, params), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: 0, errorCode: 'network', body: null };
  }
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }
  if (res.ok) return { ok: true, status: res.status, data: parsed as T };
  const raw = parsed !== null && typeof parsed === 'object' && 'error_code' in parsed ? String(parsed.error_code) : '';
  return { ok: false, status: res.status, errorCode: isErrorCode(raw) ? raw : 'unrecognised_response', body: parsed };
}
