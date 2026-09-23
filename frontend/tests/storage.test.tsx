// Main path in jsdom against the fixture-backed API double (B3 owned test
// test_no_clinical_data_in_browser_storage, runtime half). Walks sign-in -> two check runs -> evidence ->
// source viewer -> decision -> closure -> summary, then asserts nothing was written to any browser
// persistence API and the workspace token travelled only in the header.
// Mutation spot-check: in api/client.ts setWorkspaceToken, add `sessionStorage.setItem('ng', token)` ->
// the storage assertions fail (and static.test.ts fails too).
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { CONTRACT } from '../src/api/contract-data.gen';
import { setWorkspaceToken } from '../src/api/client';
import { A1, TOKEN, createFakeApi } from './fakeApi';

let idbOpen: ReturnType<typeof vi.fn>;
let cacheOpen: ReturnType<typeof vi.fn>;
let setItem: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  setWorkspaceToken(null);
  idbOpen = vi.fn();
  cacheOpen = vi.fn();
  vi.stubGlobal('indexedDB', { open: idbOpen, deleteDatabase: vi.fn(), databases: vi.fn(async () => []) });
  vi.stubGlobal('caches', { open: cacheOpen, match: vi.fn(), keys: vi.fn(async () => []) });
  setItem = vi.spyOn(Storage.prototype, 'setItem');
});
afterEach(() => {
  vi.unstubAllGlobals();
});

async function runAt(sgt: string) {
  const again = screen.queryByText('Run checks again');
  if (again) fireEvent.click(again);
  fireEvent.change(screen.getByLabelText('Check sources up to (Singapore time)'), { target: { value: sgt } });
  fireEvent.click(screen.getByRole('button', { name: 'Run checks' }));
  await screen.findByText(/Checks ran over sources up to the chosen cutoff/);
}

test('main path leaves nothing clinical in browser storage and keeps the token in memory', async () => {
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: /Dr Lim/ }));
  fireEvent.click(await screen.findByRole('button', { name: /ENC-A1/ }));
  await screen.findByText('No check run yet');

  await runAt('2026-09-21T11:30');
  await waitFor(() => expect(document.querySelector('.glance-headline')?.textContent).toBe('Closure blocked: 2 Tier 1 items with Dr Lim'));
  await runAt('2026-09-21T16:00');
  await waitFor(() => expect(document.querySelector('.glance-headline')?.textContent).toBe('Closure blocked: 3 Tier 1 items with Dr Lim'));

  // Evidence -> source viewer: the 16:00 span after an emoji is highlighted exactly.
  const diff = screen.getByRole('article', { name: 'Possibly copied-forward statement' });
  const buttons = within(diff).getAllByRole('button', { name: 'Show in source' });
  fireEvent.click(buttons[buttons.length - 1] as HTMLElement);
  await waitFor(() => expect(document.querySelector('.version-pane mark')?.textContent).toBe('Patient stable'));
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));

  // Summary before any decision.
  fireEvent.click(screen.getByRole('button', { name: 'Summary' }));
  await screen.findByText(CONTRACT.human_review_statement);

  // Decision (the double mirrors the real API; see handoff for what is executed on the real one).
  fireEvent.click(screen.getByRole('button', { name: 'Review' }));
  fireEvent.click(screen.getByRole('button', { name: 'Flags' }));
  const dose = screen.getByRole('article', { name: 'Dose differs between sources' });
  fireEvent.click(within(dose).getByRole('button', { name: 'Decide' }));
  const sheet = await screen.findByRole('dialog', { name: /Decide: Dose differs between sources/ });
  fireEvent.click(within(sheet).getByRole('radio', { name: /^Accept Records/ }));
  fireEvent.click(within(sheet).getByRole('button', { name: 'Record: accept' }));
  await screen.findByText(/Recorded: Dose differs between sources is now accepted/);
  await screen.findByText('The glance strip is not available in this build.');

  fireEvent.click(screen.getByRole('button', { name: 'Closure' }));
  await screen.findByText('Accept (open to accepted)');
  fireEvent.click(screen.getByRole('button', { name: 'Summary' }));
  await screen.findByText('Summary is not available in this build.');

  // Nothing persisted in the browser.
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
  expect(setItem).not.toHaveBeenCalled();
  expect(idbOpen).not.toHaveBeenCalled();
  expect(cacheOpen).not.toHaveBeenCalled();
  expect(document.cookie).toBe('');

  // The workspace token only ever travels in its header, never in a URL or body.
  const withToken = api.requests.filter((r) => r.headers[CONTRACT.workspace_header.toLowerCase()] === TOKEN);
  expect(withToken.length).toBeGreaterThan(10);
  expect(api.requests.filter((r) => r.url.includes(TOKEN) || JSON.stringify(r.body ?? '').includes(TOKEN))).toEqual([]);
  // Clinical text is fetched in bodies only: every URL is a contract route with opaque ids.
  expect(api.requests.every((r) => r.url.startsWith('/api/') && !/[\s"]/.test(decodeURIComponent(r.url)))).toBe(true);
});

test('a stale decision shows who decided first and records nothing', async () => {
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Dr Lim/ }));
  fireEvent.click(await screen.findByRole('button', { name: /ENC-A1/ }));
  await screen.findByText('No check run yet');
  await runAt('2026-09-21T16:00');
  const dose = await screen.findByRole('article', { name: 'Dose differs between sources' });
  fireEvent.click(within(dose).getByRole('button', { name: 'Decide' }));
  await screen.findByRole('dialog');
  // Another actor decides first, at the same revision the open sheet holds.
  const flags = await (await api.fetch(`/api/encounters/${A1}/flags`)).json();
  const flag = flags.find((f: { title: string }) => f.title === 'Dose differs between sources');
  const other = await api.fetch(`/api/encounters/${A1}/flags/${flag.flag_id}/decisions`,
    { method: 'POST', body: JSON.stringify({ action: 'accept', expected_revision: flag.revision, adjudicated_evidence: [] }) });
  expect(other.status).toBe(200);
  const sheet = screen.getByRole('dialog');
  fireEvent.click(within(sheet).getByRole('radio', { name: /^Accept Records/ }));
  fireEvent.click(within(sheet).getByRole('button', { name: 'Record: accept' }));
  const alert = await within(sheet).findByRole('alert');
  expect(alert.textContent).toContain(`Dr Lim accepted this flag at 16:05, 21 Sept before your decision was sent. It is now accepted (revision ${flag.revision + 1}).`);
  expect(alert.textContent).toContain('Your decision was not recorded');
});
