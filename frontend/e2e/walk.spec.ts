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
  const sheet = page.getByRole('dialog', { name: /Decide: Dose differs between sources/ });
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
