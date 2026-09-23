// Degraded and edge states (Review Standard S09-R01/R03, S16-R05; Section 13 inline decisions).
// Mutation spot-checks: make keepOnOutage always return `next` -> the outage case fails; treat 4xx as
// transient -> the 403 case fails; map ruleset_unapproved to an ordinary error -> the paused case fails; delete the
// SourceViewer noRun text -> the missing-version case fails; drop `slot` from FlagCard -> the inline case fails.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { setWorkspaceToken } from '../src/api/client';
import { createFakeApi } from './fakeApi';

function wide(matches: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({ matches, media: q, addEventListener: () => undefined, removeEventListener: () => undefined }));
}
beforeEach(() => setWorkspaceToken(null));
afterEach(() => vi.unstubAllGlobals());

async function openA1(isWide: boolean) {
  wide(isWide);
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Dr Lim/ }));
  fireEvent.click(await screen.findByRole('button', { name: /ENC-A1/ }));
  await screen.findByText('No check run yet');
  return api;
}
async function runAt(sgt: string) {
  const again = screen.queryByText('Run checks again');
  if (again) fireEvent.click(again);
  fireEvent.change(screen.getByLabelText('Check sources up to (Singapore time)'), { target: { value: sgt } });
  fireEvent.click(screen.getByRole('button', { name: 'Run checks' }));
  await screen.findByText(/Checks ran over sources up to the chosen cutoff/);
}

test('an outage keeps the last results readable, labelled stale with their generation time, and recovers', async () => {
  const api = await openA1(false);
  await runAt('2026-09-21T11:30');
  await waitFor(() => expect(document.querySelector('.glance-headline')?.textContent).toBe('Closure blocked: 2 Tier 1 items with Dr Lim'));
  api.outage.on = true;
  await runAt('2026-09-21T16:00');
  const alert = await screen.findByText(/The latest refresh did not complete \(HTTP 503\)/);
  expect(alert.textContent).toMatch(/check run completed \d\d:\d\d, 21 Sept, sources up to 11:30, 21 Sept\. They may be out of date\./);
  expect(document.querySelector('.glance-headline')?.textContent).toBe('Closure blocked: 2 Tier 1 items with Dr Lim');
  expect(screen.getByRole('article', { name: 'Critical result without documented response' })).toBeTruthy();
  api.outage.on = false;
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(document.querySelector('.glance-headline')?.textContent).toBe('Closure blocked: 3 Tier 1 items with Dr Lim'));
  expect(screen.queryByText(/The latest refresh did not complete/)).toBeNull();
});

test('a 403 on refresh is not an outage: earlier clinical results are removed, not kept', async () => {
  const api = await openA1(false);
  await runAt('2026-09-21T11:30');
  await screen.findByRole('article', { name: 'Critical result without documented response' });
  api.outage.on = true;
  api.outage.status = 403;
  await runAt('2026-09-21T16:00');
  await screen.findByText('Flags could not be loaded (server code forbidden_role).');
  expect(screen.queryByRole('article', { name: 'Critical result without documented response' })).toBeNull();
  expect(screen.queryByText(/The latest refresh did not complete/)).toBeNull();
});

test('an unapproved rule set pauses checks in plain words and is never shown as an outage', async () => {
  const api = await openA1(false);
  api.governance.unapproved = true;
  fireEvent.change(screen.getByLabelText('Check sources up to (Singapore time)'), { target: { value: '2026-09-21T11:30' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run checks' }));
  await screen.findByText('Checks are paused: the rule set is awaiting clinical governance approval. No check was run.');
  api.governance.unapproved = false;
  await runAt('2026-09-21T11:30');
  fireEvent.click(screen.getByRole('button', { name: 'Questions' }));
  await screen.findByText('AI drafting disabled.', { exact: false });
  // Approval withdrawn after a run (B4 re-verifies on every call): the next refresh is refused.
  api.governance.unapproved = true;
  fireEvent.click(screen.getByRole('button', { name: 'Review' }));
  const dose = screen.getByRole('article', { name: 'Dose differs between sources' });
  fireEvent.click(within(dose).getByRole('button', { name: 'Decide' }));
  const sheet = await screen.findByRole('dialog', { name: /Decide: Dose differs/ });
  fireEvent.click(within(sheet).getByRole('radio', { name: /^Accept Records/ }));
  fireEvent.click(within(sheet).getByRole('button', { name: 'Record: accept' }));
  await screen.findByText(/The glance strip is paused:/);
  expect(screen.queryByText(/The latest refresh did not complete/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Questions' }));
  const note = (await screen.findByText(/^Questions are paused:$/)).closest('.note-paused');
  expect(note?.textContent).toBe('Questions are paused: the rule set is awaiting clinical governance approval. Nothing is shown in their place.');
  expect(screen.queryByRole('heading', { name: 'Which allergy entry is correct?' })).toBeNull();
});

test('a cited source version whose text is gone shows an explicit state, not a blank', async () => {
  const api = await openA1(false);
  await runAt('2026-09-21T16:00');
  const orig = api.fetch;
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    String(input).endsWith('/text') ? Promise.resolve(new Response(JSON.stringify({ error_code: 'not_found' }), { status: 404 })) : orig(input, init)));
  const diff = screen.getByRole('article', { name: 'Possibly copied-forward statement' });
  fireEvent.click(within(diff).getAllByRole('button', { name: 'Show in source' })[0] as HTMLElement);
  await screen.findByText(/This source version is no longer available/);
  expect(document.querySelector('.version-pane mark')).toBeNull();
});

test('on wide screens the decision form renders inside the flag card', async () => {
  await openA1(true);
  await runAt('2026-09-21T16:00');
  const dose = screen.getByRole('article', { name: 'Dose differs between sources' });
  fireEvent.click(within(dose).getByRole('button', { name: 'Decide' }));
  const form = await within(dose).findByRole('form', { name: /Decide: Dose differs between sources/ });
  expect(form).toBeTruthy();
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(within(form).getByRole('radio', { name: /^Accept Records/ }));
  fireEvent.click(within(form).getByRole('button', { name: 'Record: accept' }));
  await screen.findByText(/Recorded: Dose differs between sources is now accepted/);
});

test('on wide screens, evidence opened from the Questions tab shows in the source pane', async () => {
  await openA1(true);
  await runAt('2026-09-21T16:00');
  fireEvent.click(screen.getByRole('button', { name: 'Questions' }));
  const q = (await screen.findByRole('heading', { name: 'Which allergy entry is correct?' })).closest('article') as HTMLElement;
  fireEvent.click(within(q).getAllByRole('button', { name: 'Show in source' })[0] as HTMLElement);
  await waitFor(() => expect(document.querySelector('.three-pane .version-pane mark')).not.toBeNull());
});
