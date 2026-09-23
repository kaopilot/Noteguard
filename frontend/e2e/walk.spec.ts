// B3 main path against the running API (stub engine until I1). Assertions use text unique to the
// element under test (L9). Screenshots go to test-results/ for visual review.
import { expect, test, type Page } from '@playwright/test';

const shot = (page: Page, name: string) => page.screenshot({ path: `test-results/shots/${test.info().project.name}-${name}.png` });

async function signIn(page: Page, who: RegExp) {
  await page.goto('/');
  await page.getByRole('button', { name: who }).click();
}

async function runAt(page: Page, localSgt: string) {
  const again = page.getByText('Run checks again');
  if (await again.isVisible()) await again.click();
  await page.getByLabel('Check sources up to (Singapore time)').fill(localSgt);
  await page.getByRole('button', { name: 'Run checks' }).click();
  await expect(page.getByText('Checks ran over sources up to the chosen cutoff')).toBeVisible();
}

test('main path: runs, flags, evidence, source viewer, decision, closure, summary; nothing clinical stored', async ({ page }) => {
  const mobile = test.info().project.name.startsWith('mobile');
  await signIn(page, /Dr Lim/);
  await page.getByRole('button', { name: /ENC-A1/ }).click();
  await expect(page.getByText('No check run yet')).toBeVisible();

  await runAt(page, '2026-09-21T11:30');
  await expect(page.locator('.glance-headline')).toHaveText('Closure blocked: 2 Tier 1 items with Dr Lim');

  await runAt(page, '2026-09-21T16:00');
  await expect(page.locator('.glance-headline')).toHaveText('Closure blocked: 3 Tier 1 items with Dr Lim');
  await shot(page, '01-glance-16h');

  const crit = page.getByRole('article', { name: 'Critical result without documented response' });
  await expect(crit.getByText('A later check superseded this flag')).toBeVisible();
  await expect(crit.locator('.flag-facts')).toContainText('Superseded');
  await expect(crit.locator('.tier-badge-label')).toHaveText('Tier 1');

  // Source changed since flag: cited v1 and current v2 side by side.
  const alg = page.getByRole('article', { name: 'Conflicting allergy documentation' });
  await expect(alg.getByText('Source changed since flag')).toBeVisible();
  await alg.getByRole('button', { name: 'Show in source' }).nth(1).click();
  await expect(page.getByText('Cited: version 1')).toBeVisible();
  await expect(page.getByText('Current: version 2')).toBeVisible();
  await expect(page.locator('.version-pane').first().locator('mark')).toHaveText('Allergy: Penicillin allergy — rash (per GP records)');
  await shot(page, '02-side-by-side');
  if (mobile) await page.getByRole('button', { name: 'Close' }).click();

  // Offset case: 16:00 social-work note has an astral emoji before the span.
  if (mobile) await page.getByRole('button', { name: 'Flags', exact: true }).click();
  const diff = page.getByRole('article', { name: 'Possibly copied-forward statement' });
  await diff.getByRole('button', { name: 'Show in source' }).last().click();
  await expect(page.locator('.version-pane mark')).toHaveText('Patient stable');
  await expect(page.locator('.version-pane .note-problem')).toHaveCount(0);
  await shot(page, '03-offset-highlight');
  if (mobile) await page.getByRole('button', { name: 'Close' }).click();

  // Summary works before any decision (the stub engine answers 501 after one).
  await page.getByRole('button', { name: 'Summary' }).click();
  await expect(page.getByText('Requires human review. Not the medical record. Does not diagnose or recommend treatment.')).toBeVisible();
  await shot(page, '04-summary');

  // Decision on a Tier 2 flag.
  await page.getByRole('button', { name: 'Review' }).click();
  if (mobile) await page.getByRole('button', { name: 'Flags', exact: true }).click();
  const dose = page.getByRole('article', { name: 'Dose differs between sources' });
  await dose.getByRole('button', { name: 'Decide' }).click();
  const sheet = page.getByRole('form', { name: /Decide: Dose differs between sources/ });
  await expect(sheet).toBeVisible();
  await shot(page, '05-decision-sheet');
  await sheet.getByRole('radio', { name: /^Accept Records/ }).check();
  await sheet.getByRole('button', { name: 'Record: accept' }).click();
  await expect(page.getByText(/Recorded: Dose differs between sources is now accepted/)).toBeVisible();
  await expect(page.getByText('The glance strip is not available in this build.')).toBeVisible();

  await page.getByRole('button', { name: 'Closure' }).click();
  await expect(page.locator('.closure-headline')).toHaveText('Closure blocked');
  await expect(page.locator('table.decisions')).toContainText('Accept (open to accepted)');
  await page.getByRole('button', { name: 'Check closure now' }).click();
  await expect(page.getByText(/Closure is blocked\. The server lists/)).toBeVisible();
  await shot(page, '06-closure');

  await page.getByRole('button', { name: 'Summary' }).click();
  await expect(page.getByText('Summary is not available in this build.')).toBeVisible();

  if (mobile) {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  }

  // Browser persistence after the whole path: nothing in Web Storage or IndexedDB, and the SW cache
  // holds shell files only.
  await page.evaluate(() => navigator.serviceWorker.ready);
  const stored = await page.evaluate(async () => {
    const dbs = 'databases' in indexedDB ? await indexedDB.databases() : [];
    const cached: string[] = [];
    for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) cached.push(new URL(r.url).pathname);
    return { local: localStorage.length, session: sessionStorage.length, dbs: dbs.length, cookie: document.cookie, cached };
  });
  expect(stored.local).toBe(0);
  expect(stored.session).toBe(0);
  expect(stored.dbs).toBe(0);
  expect(stored.cookie).not.toContain('ng_session');
  expect(stored.cached.length).toBeGreaterThan(0);
  expect(stored.cached.filter((p) => p.startsWith('/api'))).toEqual([]);
  test.info().annotations.push({ type: 'sw-cache', description: stored.cached.join(' ') });
});

test('care-team scope: a clinician outside the team sees no encounters', async ({ page }) => {
  await signIn(page, /Dr Kaur/);
  await expect(page.getByText('No encounters are available to you.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reset case' })).toHaveCount(0);
});

test('offline: the shell says clinical content is not stored', async ({ page, context }) => {
  await page.goto('/');
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline — clinical content is not stored on this device.').first()).toBeVisible();
  await shot(page, '07-offline');
  await context.setOffline(false);
});

test('documents, export and install: PDF via one-time token, clipboard copy, print layout, installability', async ({ page, context }) => {
  const mobile = test.info().project.name.startsWith('mobile');
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await signIn(page, /Dr Lim/);
  await page.getByRole('button', { name: /ENC-A1/ }).click();
  await runAt(page, '2026-09-21T16:00');

  // PDF original through the single-use, no-store document token.
  if (mobile) await page.getByRole('button', { name: 'Record', exact: true }).click();
  await page.getByRole('button', { name: 'Outside referral letter' }).click();
  await expect(page.getByText(/^PDF, 1 page\./)).toBeVisible();
  const [doc] = await Promise.all([
    context.waitForEvent('response', (r) => r.url().includes('/api/documents/')),
    page.getByRole('button', { name: 'Open the original PDF' }).click(),
  ]);
  expect(doc.status()).toBe(200);
  expect(doc.headers()['content-type']).toContain('application/pdf');
  expect(doc.headers()['cache-control']).toContain('no-store');
  const again = await page.request.get(doc.url());
  expect(again.status()).toBeGreaterThanOrEqual(400);
  test.info().annotations.push({ type: 'document-token-reuse', description: String(again.status()) });
  if (mobile) await page.getByRole('button', { name: 'Close' }).click();

  // Scanned PDF: never looks complete.
  await page.getByRole('button', { name: 'Scanned outside lab report' }).click();
  await expect(page.getByText('No text could be extracted from this document. Review the original.')).toBeVisible();
  if (mobile) await page.getByRole('button', { name: 'Close' }).click();

  // Copy and print.
  await page.getByRole('button', { name: 'Summary' }).click();
  await page.getByRole('button', { name: 'Copy summary' }).click();
  await expect(page.getByText('Summary copied as plain text with its citations.')).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied.startsWith('Requires human review. Not the medical record. Does not diagnose or recommend treatment.')).toBe(true);
  expect(copied).toContain('\u201cPatient stable\u201d');
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.app-bar')).toBeHidden();
  await expect(page.locator('.glance')).toBeHidden();
  await expect(page.locator('.summary-statement')).toBeVisible();
  await shot(page, '08-print');
  await page.emulateMedia({ media: 'screen' });

  if (!mobile) {
    await page.evaluate(() => navigator.serviceWorker.ready);
    const cdp = await context.newCDPSession(page);
    // Playwright contexts are incognito-like and Chrome never installs from incognito, so that one
    // environment error is excluded; any app-side criterion (manifest, icons, SW) has its own error id.
    const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
    expect(installabilityErrors.map((e) => e.errorId).filter((id) => id !== 'in-incognito')).toEqual([]);
    const manifest = await cdp.send('Page.getAppManifest');
    expect(manifest.errors).toEqual([]);
    expect(manifest.url).toContain('/manifest.webmanifest');
  }
});

test('add sources: paste, new version, real PDFs (text and scanned), non-PDF refused; timeline and run control follow', async ({ page }) => {
  const mobile = test.info().project.name.startsWith('mobile');
  const pdf = (name: string) => `${process.cwd()}/../fixtures/pdfs/${name}`;
  await signIn(page, /Dr Lim/);
  await page.getByRole('button', { name: /ENC-A1/ }).click();
  const add = async () => {
    await page.getByRole('button', { name: 'Add a source' }).click();
    return page.getByRole('dialog', { name: 'Add a source' });
  };

  let d = await add();
  await d.getByLabel('Title').fill('Evening nursing note');
  await d.getByLabel('Clinical time of the note (Singapore time)').fill('2026-09-21T16:30');
  await d.getByLabel('Note text').fill('Evening review: comfortable \u{1F642}, family (家人) updated. Plan unchanged.');
  await shot(page, '09-add-source');
  await d.getByRole('button', { name: 'Add source' }).click();
  await expect(page.getByText(/^Added: Evening nursing note \(version 1\), recorded /)).toBeVisible();

  d = await add();
  const amend = d.getByLabel('New source or new version');
  const value = await d.locator('option', { hasText: 'New version of: Ward round' }).getAttribute('value');
  await amend.selectOption(value ?? '');
  await expect(d.getByLabel('Title')).toBeDisabled();
  await d.getByLabel('Note text').fill('Ward round addendum: plan unchanged after review.');
  await d.getByRole('button', { name: 'Add version 2' }).click();
  await expect(page.getByText(/^Added: Ward round \(version 2\)/)).toBeVisible();

  const uploads: [string, string][] = [
    ['Referral letter (resent)', 'ENC-A1_referral_letter.pdf'],
    ['Lab report scan (resent)', 'ENC-A1_outside_lab_report_scanned.pdf'],
  ];
  for (const [title, file] of uploads) {
    d = await add();
    await d.getByRole('radio', { name: /Upload a PDF/ }).check();
    await d.getByLabel('Title').fill(title);
    await d.getByLabel('PDF file').setInputFiles(pdf(file));
    await d.getByRole('button', { name: 'Add source' }).click();
    await expect(page.getByText(new RegExp(`^Added: ${title.replace(/[()]/g, '\\$&')} \\(version 1\\)`))).toBeVisible();
  }

  d = await add();
  await d.getByRole('radio', { name: /Upload a PDF/ }).check();
  await d.getByLabel('Title').fill('Not really a PDF');
  await d.getByLabel('PDF file').setInputFiles({ name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('hello, plain text') });
  await d.getByRole('button', { name: 'Add source' }).click();
  await expect(d.getByText('This file is not a PDF. Nothing was added.')).toBeVisible();
  await d.getByRole('button', { name: 'Close' }).click();

  if (mobile) await page.getByRole('button', { name: 'Record', exact: true }).click();
  const row = (t: string) => page.locator('li.tl-row', { has: page.getByRole('button', { name: t, exact: true }) });
  await expect(row('Evening nursing note')).toContainText('Typed text');
  await expect(row('Referral letter (resent)')).toContainText('Text fully extracted');
  await expect(row('Lab report scan (resent)')).toContainText('No text layer');
  await expect(page.locator('li.tl-row', { hasText: 'Amended: version 2' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Evening nursing note', exact: true }).click();
  await expect(page.getByTestId('source-text')).toContainText('comfortable \u{1F642}, family (家人) updated');
  await shot(page, '10-added-in-viewer');
  if (mobile) await page.getByRole('button', { name: 'Close' }).click();

  const cutoff = await page.getByLabel('Check sources up to (Singapore time)').inputValue();
  expect(cutoff > '2026-09-22').toBe(true);
  await page.getByRole('button', { name: 'Run checks' }).click();
  const outcome = page.getByText(/Checks ran over sources up to the chosen cutoff|Running checks is not available in this build|Checks did not run/);
  await expect(outcome).toBeVisible();
  test.info().annotations.push({ type: 'run-after-intake', description: (await outcome.textContent()) ?? '' });
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});

test('feedback after a decision (B2 route) and the aggregate page for a governance role (B4 route)', async ({ page }) => {
  await signIn(page, /Dr Lim/);
  await page.getByRole('button', { name: /ENC-A1/ }).click();
  await runAt(page, '2026-09-21T16:00');
  const dose = page.getByRole('article', { name: 'Dose differs between sources' });
  await expect(dose.getByText(/Was this flag useful\?/)).toHaveCount(0);
  await dose.getByRole('button', { name: 'Decide' }).click();
  const form = page.getByRole('form', { name: /Decide: Dose differs between sources/ });
  await form.getByRole('radio', { name: /^Accept Records/ }).check();
  await form.getByRole('button', { name: 'Record: accept' }).click();
  await expect(page.getByText(/Recorded: Dose differs between sources is now accepted/)).toBeVisible();
  const card = page.getByRole('article', { name: 'Dose differs between sources' });
  await card.getByRole('radio', { name: 'Not useful' }).check();
  const [fb] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/feedback')),
    card.getByRole('button', { name: 'Send feedback' }).click(),
  ]);
  expect(fb.status()).toBe(201);
  const sent = fb.request().postDataJSON();
  expect(sent.usefulness).toBe('not_useful');
  expect(typeof sent.time_on_screen_ms).toBe('number');
  await expect(card.getByText(/^Feedback recorded: Not useful\./)).toBeVisible();
  await shot(page, '11-feedback');

  await page.getByRole('button', { name: 'Sign out' }).click();
  const [agg] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/aggregate/risk')),
    page.getByRole('button', { name: /Quality & Risk/ }).click(),
  ]);
  expect(agg.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Flag patterns across encounters' })).toBeVisible();
  await expect(page.getByText(/^Fewer than \d+ are shown as “<\d+”$/)).toBeVisible();
  expect(await page.locator('body').textContent()).not.toContain('ENC-A1');
  await shot(page, '12-aggregate');
});
