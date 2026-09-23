// Aggregate page (CCR-04 approved; built on a local stand-in type until `make types`).
// Mutation spot-checks: show the page to every role -> case 2 fails; add a totals row -> case 1 fails;
// parse counts as numbers -> case 1 fails ("<5" must stay as served).
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { setWorkspaceToken } from '../src/api/client';
import { A1, createFakeApi } from './fakeApi';

beforeEach(() => setWorkspaceToken(null));
afterEach(() => vi.unstubAllGlobals());

test('a governance role lands on the aggregate page: counts as served, "<5" kept, no totals, no identifiers', async () => {
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Quality & Risk/ }));
  await screen.findByRole('heading', { name: 'Flag patterns across encounters' });
  const table = await screen.findByRole('table');
  const rows = within(table).getAllByRole('row').slice(1).map((r) => Array.from(r.querySelectorAll('td')).map((td) => td.textContent));
  expect(rows).toEqual([
    ['ALG-001', 'Tier 1', 'Open', '<4h', '<5'],
    ['DOSE-001', 'Tier 2', 'Open', '<4h', '12'],
  ]);
  expect(screen.getByText('Fewer than 5 are shown as “<5”')).toBeTruthy();
  expect(document.body.textContent).not.toContain(A1);
  expect(document.body.textContent).not.toContain('ENC-A1');
  expect(screen.queryByRole('button', { name: /ENC-A1/ })).toBeNull();
});

test('a clinician is not shown the aggregate page and never requests it', async () => {
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Dr Lim/ }));
  await screen.findByRole('button', { name: /ENC-A1/ });
  expect(screen.queryByRole('heading', { name: 'Flag patterns across encounters' })).toBeNull();
  expect(api.requests.some((r) => r.url.includes('/aggregate/'))).toBe(false);
});
