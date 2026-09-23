// Service worker policy (Section 10.2; B3 owned test test_sw_never_caches_api). Runs public/sw.js
// in a fake worker scope, with the shell list injected the same way the build does.
// Mutation spot-check: delete `if (isApi(url)) return;` -> the /api/ navigation case fails.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import { expect, test, vi } from 'vitest';

const SRC = readFileSync(resolve(__dirname, '..', 'public', 'sw.js'), 'utf-8');
const ORIGIN = 'https://noteguard.test';

function loadWorker(shell: string[]) {
  const handlers: Record<string, (e: unknown) => void> = {};
  const cache = { addAll: vi.fn(async () => undefined), put: vi.fn(async () => undefined), keys: vi.fn(async () => []) };
  const caches = {
    open: vi.fn(async () => cache),
    match: vi.fn(async () => new Response('cached')),
    keys: vi.fn(async () => ['noteguard-shell-old']),
    delete: vi.fn(async () => true),
  };
  const fetch = vi.fn(async () => new Response('net'));
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (t: string, h: (e: unknown) => void) => { handlers[t] = h; },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  } as Record<string, unknown>;
  const injected = SRC.replace('self.__SHELL__ = [];', `self.__SHELL__ = ${JSON.stringify(shell)};`)
    .replace("self.__SHELL_VERSION__ = 'dev';", "self.__SHELL_VERSION__ = 't1';");
  expect(injected).not.toBe(SRC);
  runInNewContext(injected, { self, caches, fetch, URL, Response, Promise });
  const dispatchFetch = (path: string, method = 'GET', mode = 'cors') => {
    const respondWith = vi.fn();
    handlers.fetch?.({ request: { url: ORIGIN + path, method, mode }, respondWith });
    return respondWith;
  };
  return { handlers, cache, caches, fetch, dispatchFetch };
}

test('requests under /api/ are never answered from or written to the cache', async () => {
  const w = loadWorker(['/offline.html', '/assets/index-abc.js', '/api/encounters']);
  const apiCases: [string, string, string][] = [
    ['/api/encounters/e1/flags', 'GET', 'cors'],
    ['/api/encounters/e1/source-versions/v1/text', 'GET', 'cors'],
    ['/api/session', 'POST', 'cors'],
    ['/api/documents/tok123', 'GET', 'navigate'],
    ['/api/encounters', 'GET', 'cors'],
    ['/api', 'GET', 'navigate'],
  ];
  for (const [path, method, mode] of apiCases) expect(w.dispatchFetch(path, method, mode)).not.toHaveBeenCalled();
  expect(w.caches.match).not.toHaveBeenCalled();
  expect(w.fetch).not.toHaveBeenCalled();
  expect(w.cache.put).not.toHaveBeenCalled();
});

test('install precaches only the listed shell, never an /api/ path, and nothing writes at runtime', async () => {
  const w = loadWorker(['/offline.html', '/assets/index-abc.js', '/api/encounters']);
  let pending: Promise<unknown> = Promise.resolve();
  w.handlers.install?.({ waitUntil: (p: Promise<unknown>) => { pending = p; } });
  await pending;
  expect(w.cache.addAll).toHaveBeenCalledWith(['/offline.html', '/assets/index-abc.js']);
  const shellHit = w.dispatchFetch('/assets/index-abc.js');
  expect(shellHit).toHaveBeenCalledTimes(1);
  expect(w.dispatchFetch('/assets/not-in-shell.js')).not.toHaveBeenCalled();
  expect(w.dispatchFetch('/assets/index-abc.js', 'POST')).not.toHaveBeenCalled();
  expect(w.cache.put).not.toHaveBeenCalled();
  expect(SRC).not.toMatch(/\.put\s*\(/);
});

test('an offline navigation gets the static offline page', async () => {
  const w = loadWorker(['/offline.html']);
  w.fetch.mockRejectedValueOnce(new TypeError('offline'));
  const rw = w.dispatchFetch('/', 'GET', 'navigate');
  expect(rw).toHaveBeenCalledTimes(1);
  await rw.mock.calls[0]?.[0];
  expect(w.caches.match).toHaveBeenCalledWith('/offline.html');
  const offline = readFileSync(resolve(__dirname, '..', 'public', 'offline.html'), 'utf-8');
  expect(offline).toContain('Offline — clinical content is not stored on this device.');
});
