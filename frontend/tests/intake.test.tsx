// Add-source UI (Section 13 intake; B2's intake rules). Mutation spot-checks: regenerate the key on
// every submit -> the retry case fails; send identifier_namespace always -> the new-version case fails;
// drop `disabled={amending !== null}` from Title -> the new-version case fails; delete the
// pdf_not_a_pdf message -> the PDF case fails; drop the RunControl key -> the cutoff case fails.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { setWorkspaceToken } from '../src/api/client';
import { sgtInputToUtc } from '../src/lib/time';
import { A1, createFakeApi } from './fakeApi';

beforeEach(() => setWorkspaceToken(null));
afterEach(() => vi.unstubAllGlobals());

async function openA1() {
  const api = createFakeApi();
  vi.stubGlobal('fetch', vi.fn(api.fetch));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Dr Lim/ }));
  fireEvent.click(await screen.findByRole('button', { name: /ENC-A1/ }));
  await screen.findByText('No check run yet');
  fireEvent.click(screen.getByRole('button', { name: 'Add a source' }));
  const dialog = await screen.findByRole('dialog', { name: 'Add a source' });
  return { api, dialog };
}
const sourcePosts = (api: ReturnType<typeof createFakeApi>) => api.requests.filter((r) => r.method === 'POST' && /\/sources(\/pdf)?$/.test(r.url));
const NOTE = 'Evening review: patient comfortable, eating and drinking. Plan unchanged.';

test('a pasted note is added by a care-team author, appears in the timeline, and its text travels only in the body', async () => {
  const { api, dialog } = await openA1();
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Evening nursing note' } });
  fireEvent.change(within(dialog).getByLabelText('Clinical time of the note (Singapore time)'), { target: { value: '2026-09-21T16:30' } });
  fireEvent.change(within(dialog).getByLabelText('Note text'), { target: { value: NOTE } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add source' }));
  await screen.findByText(/^Added: Evening nursing note \(version 1\), recorded .*Run checks up to that time or later to include it\.$/);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));
  expect(screen.getByRole('button', { name: 'Evening nursing note' })).toBeTruthy();
  const [post] = sourcePosts(api);
  expect(post?.url).toBe(`/api/encounters/${A1}/sources`);
  expect(post?.body.text).toBe(NOTE);
  expect(post?.body.source_time).toBe('2026-09-21T08:30:00Z');
  expect(post?.body.idempotency_key).toMatch(/^ui-[0-9a-f]{32}$/);
  expect('identifier_namespace' in (post?.body ?? {})).toBe(false);
  expect(api.requests.some((r) => decodeURIComponent(r.url).includes('comfortable'))).toBe(false);
});

test('the run control defaults to a cutoff that includes a newly recorded source', async () => {
  const { api, dialog } = await openA1();
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Late note' } });
  fireEvent.change(within(dialog).getByLabelText('Note text'), { target: { value: NOTE } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add source' }));
  await screen.findByText(/^Added: Late note/);
  const recorded = api.added[0]?.view.version_time as string;
  // The property that matters: the default cutoff is at or after the moment the source was recorded.
  await waitFor(() => {
    const value = (screen.getByLabelText('Check sources up to (Singapore time)') as HTMLInputElement).value;
    const cutoff = sgtInputToUtc(value);
    expect(cutoff).not.toBeNull();
    expect(Date.parse(cutoff ?? '')).toBeGreaterThanOrEqual(Date.parse(recorded));
    expect(Date.parse(cutoff ?? '') - Date.parse(recorded)).toBeLessThan(1000);
  });
});

test('a retry after a lost connection reuses the idempotency key; changing the note issues a new one', async () => {
  const { api, dialog } = await openA1();
  api.network.failNextPosts = 2;
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Evening nursing note' } });
  fireEvent.change(within(dialog).getByLabelText('Note text'), { target: { value: NOTE } });
  const add = within(dialog).getByRole('button', { name: 'Add source' });
  fireEvent.click(add);
  await within(dialog).findByText(/Submitting again is safe/);
  fireEvent.click(add);
  await waitFor(() => expect(sourcePosts(api)).toHaveLength(2));
  fireEvent.change(within(dialog).getByLabelText('Note text'), { target: { value: NOTE + ' Family updated.' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add source' }));
  await screen.findByText(/^Added: Evening nursing note \(version 1\)/);
  const keys = sourcePosts(api).map((r) => r.body.idempotency_key);
  expect(keys).toHaveLength(3);
  expect(keys[1]).toBe(keys[0]);
  expect(keys[2]).not.toBe(keys[1]);
  expect(api.added).toHaveLength(1);
});

test('a new version keeps the original metadata locked and sends no namespace', async () => {
  const { api, dialog } = await openA1();
  const select = within(dialog).getByLabelText('New source or new version') as HTMLSelectElement;
  const option = within(select).getByRole('option', { name: /^New version of: Ward round/ }) as HTMLOptionElement;
  fireEvent.change(select, { target: { value: option.value } });
  const title = within(dialog).getByLabelText('Title') as HTMLInputElement;
  expect(title.value).toBe('Ward round');
  expect(title.disabled).toBe(true);
  expect((within(dialog).getByLabelText('Author (accountable care-team member)') as HTMLSelectElement).disabled).toBe(true);
  expect((within(dialog).getByLabelText('Clinical time of the note (Singapore time)') as HTMLInputElement).disabled).toBe(true);
  fireEvent.change(within(dialog).getByLabelText('Note text'), { target: { value: 'Ward round (corrected): plan unchanged.' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add version 2' }));
  await screen.findByText(/^Added: Ward round \(version 2\)/);
  const [post] = sourcePosts(api);
  expect(post?.body.source_id).toBe(option.value);
  expect('identifier_namespace' in (post?.body ?? {})).toBe(false);
});

test('a PDF that is not a PDF is refused with a reason, and a timed-out PDF is kept and labelled', async () => {
  const { dialog } = await openA1();
  fireEvent.click(within(dialog).getByRole('radio', { name: /Upload a PDF/ }));
  fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Outside scan' } });
  const input = within(dialog).getByLabelText('PDF file');
  fireEvent.change(input, { target: { files: [new File(['hello'], 'note.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add source' }));
  await within(dialog).findByText('This file is not a PDF. Nothing was added.');
  fireEvent.change(input, { target: { files: [new File(['%PDF-1.4 scanned'], 'slow-scan.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add source' }));
  await screen.findByText(/The PDF was kept, but reading its text did not finish in time/);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));
  const row = screen.getByRole('button', { name: 'Outside scan' }).closest('li') as HTMLElement;
  expect(row.textContent).toContain('Extraction did not complete');
});
