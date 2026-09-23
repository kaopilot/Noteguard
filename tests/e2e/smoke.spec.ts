// I1 end-to-end smoke (Section 12.4; owner I1): one walk of the main path on the real engine behind the
// approval-gated API and the built frontend. Every assertion is scoped to the element under test and uses
// text unique to it (L9). Nothing here logs note text.
import { expect, test } from '@playwright/test';
import path from 'node:path';

const CRIT = 'Critical result without documented response';
const ALG = 'Conflicting allergy documentation';
const SCAN = path.resolve(__dirname, '../../fixtures/pdfs/ENC-A1_outside_lab_report_scanned.pdf');

test('I1 smoke: intake, conflict, critical, decision and closure, summary, out-of-scope refusal', async ({ page, browser }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Dr Lim/ }).click();
  await page.getByRole('button', { name: /ENC-A1/ }).click();
  // View switches are scoped to the tab bar with exact names (a blocker row may carry its own 'Review…' button).
  const tab = (name: string) => page.getByRole('navigation', { name: 'Encounter views' }).getByRole('button', { name, exact: true });
  const add = async () => {
    await page.getByRole('button', { name: 'Add a source' }).click();
    return page.getByRole('dialog', { name: 'Add a source' });
  };

  // 1. Multidisciplinary intake: a pasted note and the scanned PDF.
  let d = await add();
  await d.getByLabel('Title').fill('I1 smoke evening note');
  await d.getByLabel('Clinical time of the note (Singapore time)').fill('2026-09-21T16:45');
  await d.getByLabel('Note text').fill('Evening check: comfortable, plan unchanged.');
  await d.getByRole('button', { name: 'Add source' }).click();
  await expect(page.getByText(/^Added: I1 smoke evening note \(version 1\)/)).toBeVisible();
  d = await add();
  await d.getByRole('radio', { name: /Upload a PDF/ }).check();
  await d.getByLabel('Title').fill('I1 smoke scanned lab report');
  await d.getByLabel('PDF file').setInputFiles(SCAN);
  await d.getByRole('button', { name: /^(Add source|Upload)/ }).click();
  await expect(page.getByText(/^Added: I1 smoke scanned lab report \(version 1\)/)).toBeVisible();

  // Run at 11:30 (CRIT-001 is raised at this cutoff).
  await page.getByLabel('Check sources up to (Singapore time)').fill('2026-09-21T11:30');
  await page.getByRole('button', { name: 'Run checks' }).click();
  await expect(page.getByText('Checks ran over sources up to the chosen cutoff')).toBeVisible();

  // 2. Conflict flag: the ALG-001 card (Tier 1) and its question bubble. The flag's own `question` is null;
  //    the question is a bubble (q_allergy_which_correct), matched by its EXACT full text (never a substring).
  const alg = page.getByRole('article', { name: ALG });
  await expect(alg.locator('.tier-badge-label')).toHaveText('Tier 1');
  await expect(page.getByText('Which allergy entry is correct?', { exact: true }).first()).toBeVisible();

  // 3. Critical flag with its evidence and owner.
  const crit = page.getByRole('article', { name: CRIT });
  await expect(crit.locator('.tier-badge-label')).toHaveText('Tier 1');
  await expect(crit.getByText('Potassium 6.4 mmol/L').first()).toBeVisible();
  await expect(crit.locator('.flag-facts')).toContainText('Dr Lim');

  // 4. Human decision and its effect on closure: accepted still blocks; resolved does not.
  const blocker = page.locator('.closure-list li', { hasText: CRIT });
  const decideCrit = async (radio: RegExp) => {
    await page.getByRole('article', { name: CRIT }).getByRole('button', { name: 'Decide' }).click();
    const sheet = page.getByRole('form', { name: new RegExp(`Decide: ${CRIT}`) });
    await sheet.getByRole('radio', { name: radio }).check();
    return sheet;
  };
  let sheet = await decideCrit(/^Accept Records/);
  await sheet.getByRole('button', { name: 'Record: accept' }).click();
  await expect(page.getByText(new RegExp(`Recorded: ${CRIT} is now accepted`))).toBeVisible();
  await tab('Closure').click();
  await expect(page.locator('.closure-headline')).toHaveText('Closure blocked');
  await expect(blocker).toHaveCount(1);
  await tab('Review').click();
  sheet = await decideCrit(/^Resolve/);
  const reason = sheet.getByRole('combobox', { name: /^Reason code/ }); // the radios' labels also mention a reason code
  const values = await reason.locator('option').evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value).filter(Boolean));
  await reason.selectOption(values.includes('already_addressed_in_source') ? 'already_addressed_in_source' : values[0]);
  await sheet.getByRole('button', { name: 'Record: resolve' }).click();
  await expect(page.getByText(new RegExp(`Recorded: ${CRIT} is now resolved`))).toBeVisible();
  await tab('Closure').click();
  await expect(blocker).toHaveCount(0);
  await expect(page.locator('.closure-headline')).toHaveText('Closure blocked'); // ALG-001 still blocks

  // 5. Summary carries the human-review statement.
  await tab('Summary').click();
  await expect(page.getByText('Requires human review. Not the medical record. Does not diagnose or recommend treatment.')).toBeVisible();

  // 6. Out of scope: a clinician outside the care team is refused (fresh browser context).
  const other = await browser.newPage({ baseURL: 'http://127.0.0.1:4173' });
  await other.goto('/');
  await other.getByRole('button', { name: /Dr Kaur/ }).click();
  await expect(other.getByText('No encounters are available to you.')).toBeVisible();
  await expect(other.getByRole('button', { name: /ENC-A1/ })).toHaveCount(0);
  await other.close();
});
