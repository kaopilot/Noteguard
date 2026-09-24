// Usefulness feedback (B3 owns it, @kaopilot 23 Sep). Mutation spot-checks: show the control on undecided
// flags -> case 1 fails; send a made-up time instead of the measured one -> case 1 fails; drop the
// corrected owner -> case 2 fails; allow a second post -> case 1 fails.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { setWorkspaceToken } from '../src/api/client';
import { createFakeApi } from './fakeApi';

type IOCallback = (entries: { isIntersecting: boolean; intersectionRatio: number }[]) => void;
const observed = new Map<Element, IOCallback>();
let clock = 0;

beforeEach(() => {
  setWorkspaceToken(null);
  observed.clear();
  clock = 1000;
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
});
afterEach(() => vi.unstubAllGlobals());

function withIntersectionObserver() {
  vi.stubGlobal('IntersectionObserver', class {
    private cb: IOCallback;
    constructor(cb: IOCallback) { this.cb = cb; }
    observe(el: Element) { observed.set(el, this.cb); }
    disconnect() {}
  });
}

async function decideDose() {
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Dr Lim/ }));
  fireEvent.click(await screen.findByRole('button', { name: /ENC-A1/ }));
  await screen.findByText('No check run yet');
  fireEvent.change(screen.getByLabelText('Check sources up to (Singapore time)'), { target: { value: '2026-09-21T16:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run checks' }));
  const dose = await screen.findByRole('article', { name: 'Dose differs between sources' });
  expect(within(dose).queryByText(/Was this flag useful\?/)).toBeNull();
  fireEvent.click(within(dose).getByRole('button', { name: 'Decide' }));
  const sheet = await screen.findByRole('dialog', { name: /Decide: Dose differs/ });
  fireEvent.click(within(sheet).getByRole('radio', { name: /^Accept Records/ }));
  fireEvent.click(within(sheet).getByRole('button', { name: 'Record: accept' }));
  await screen.findByText(/Recorded: Dose differs between sources is now accepted/);
  const card = await screen.findByRole('article', { name: 'Dose differs between sources' });
  await within(card).findByText(/Was this flag useful\?/);
  return { api, card };
}

test('feedback appears only after a decision, sends the measured time on screen once, and says it does not change the flag', async () => {
  withIntersectionObserver();
  const { api, card } = await decideDose();
  // The card was visible for 3.2 s (simulated observer + clock), then scrolled away.
  const cb = observed.get(card);
  expect(cb).toBeDefined();
  act(() => cb?.([{ isIntersecting: true, intersectionRatio: 1 }]));
  clock += 3200;
  act(() => cb?.([{ isIntersecting: false, intersectionRatio: 0 }]));
  clock += 5000;
  fireEvent.click(within(card).getByRole('radio', { name: 'Not useful' }));
  fireEvent.click(within(card).getByRole('button', { name: 'Send feedback' }));
  const done = await within(card).findByRole('status');
  expect(done.textContent).toMatch(/^Feedback recorded: Not useful\. It informs governance\s+review of the rules; it does not change this flag\.$/);
  const posts = api.requests.filter((r) => r.method === 'POST' && r.url.endsWith('/feedback'));
  expect(posts).toHaveLength(1);
  expect(posts[0]?.body).toEqual({ flag_id: expect.any(String), usefulness: 'not_useful', time_on_screen_ms: 3200, corrected_owner_staff_id: null });
  expect(within(card).queryByRole('button', { name: 'Send feedback' })).toBeNull();
  expect(card.querySelector('.flag-facts')?.textContent).toContain('Accepted');
});

test('wrong owner can name a care-team member; without an observer the time is sent as unknown', async () => {
  vi.stubGlobal('IntersectionObserver', undefined);
  const { api, card } = await decideDose();
  fireEvent.click(within(card).getByRole('radio', { name: 'Wrong owner' }));
  const owner = within(card).getByLabelText('Who should own it? (optional)') as HTMLSelectElement;
  const tan = within(owner).getByRole('option', { name: 'Nurse Tan' }) as HTMLOptionElement;
  fireEvent.change(owner, { target: { value: tan.value } });
  fireEvent.click(within(card).getByRole('button', { name: 'Send feedback' }));
  await within(card).findByText(/Feedback recorded: Wrong owner \(should be Nurse Tan\)/);
  const post = api.requests.find((r) => r.method === 'POST' && r.url.endsWith('/feedback'));
  expect(post?.body.corrected_owner_staff_id).toBe(tan.value);
  expect(post?.body.time_on_screen_ms).toBeNull();
  await waitFor(() => expect(api.feedback).toHaveLength(1));
});
