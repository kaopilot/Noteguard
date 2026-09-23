// Static guards over product source (frontend/src). B3 owned: test_no_dangerously_set_inner_html and
// the static half of test_no_clinical_data_in_browser_storage.
// Mutation spot-checks: add `<div dangerouslySetInnerHTML={{ __html: x }} />` to any component, or
// `sessionStorage.setItem('t', token)` to api/client.ts -> the matching case fails.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, test } from 'vitest';

const SRC = resolve(__dirname, '..', 'src');
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx|js|jsx)$/.test(n) && !n.endsWith('.gen.ts') ? [p] : [];
  });
}
const SOURCES = files(SRC).map((p) => [p.slice(SRC.length + 1), readFileSync(p, 'utf-8')] as const);

test('no raw HTML injection anywhere in frontend/src', () => {
  expect(SOURCES.length).toBeGreaterThan(10);
  const hits = SOURCES.filter(([, s]) => /dangerouslySetInnerHTML|\.innerHTML\s*=|outerHTML|insertAdjacentHTML|document\.write/.test(s)).map(([p]) => p);
  expect(hits).toEqual([]);
});

test('no browser persistence API is referenced in frontend/src', () => {
  const hits = SOURCES.filter(([, s]) => /\b(localStorage|sessionStorage|indexedDB|IDBFactory|document\.cookie|caches\.)/.test(s)).map(([p]) => p);
  expect(hits).toEqual([]);
});

test('no console logging in frontend/src', () => {
  expect(SOURCES.filter(([, s]) => /\bconsole\./.test(s)).map(([p]) => p)).toEqual([]);
});
