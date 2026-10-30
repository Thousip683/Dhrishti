import { expect, test, type Page } from '@playwright/test';

async function navigate(page: Page, label: string) {
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('navigation').getByRole('link', { name: label, exact: true }).click();
}
async function start(page: Page) {
  await page.goto('/');
  await page.getByLabel('Your timezone').fill('Asia/Kolkata');
  await page.getByRole('button', { name: 'Start my session' }).click();
  await expect(page.getByRole('heading', { name: 'Your footprint at a glance' })).toBeVisible();
  const session = await (await page.request.get('/api/v1/browser/session')).json();
  await navigate(page, 'Log activity');
  await expect(page.getByLabel('Travel mode')).toBeVisible();
  return `/api/v1/sessions/${session.session_id}`;
}
async function preview(page: Page) {
  await page.getByRole('button', { name: 'Preview estimate' }).click();
  await expect(page.getByRole('button', { name: 'Save activity', exact: true })).toBeVisible();
}
async function save(page: Page) {
  await page.getByRole('button', { name: 'Save activity', exact: true }).click();
  await expect(page.getByText('Activity saved', { exact: true })).toBeVisible();
}

test('four categories preview separately and save into history and dashboard', async ({ page }) => {
  const base = await start(page);
  await page.getByLabel('Travel mode').selectOption('bus');
  await page.getByLabel('Distance travelled (km)').fill('12');
  await preview(page);
  expect((await (await page.request.get(base + '/activities')).json()).items).toHaveLength(0);
  await page.getByLabel('Distance travelled (km)').fill('8');
  await expect(page.getByRole('button', { name: 'Save activity', exact: true })).toHaveCount(0);
  await page.getByLabel('Distance travelled (km)').fill('12');
  await preview(page); await save(page);

  await page.getByRole('button', { name: 'Electricity', exact: true }).click();
  await page.getByLabel('Reference grid').selectOption('UK');
  await page.getByRole('radio', { name: 'Appliance power and time' }).check();
  await page.getByLabel('Power measurement').selectOption('average');
  await page.getByLabel('Electrical input power (kW)').fill('1.5');
  await page.getByLabel('Hours used').fill('4');
  await preview(page);
  await expect(page.getByText('6.000000 kWh', { exact: true })).toBeVisible();
  await save(page);

  await page.getByRole('button', { name: 'Food', exact: true }).click();
  await page.getByLabel('Defined meal recipe').selectOption('pea_rice_bowl');
  await page.getByRole('checkbox').check();
  await preview(page); await save(page);

  await page.getByRole('button', { name: 'Waste', exact: true }).click();
  await page.getByLabel('Waste material').selectOption('paper');
  expect(await page.getByLabel('Treatment route').locator('option').allTextContents()).not.toContain('Compost');
  await page.getByLabel('Waste material').selectOption('food');
  await page.getByLabel('Treatment route').selectOption('compost');
  await page.getByLabel('Waste mass (kg)').fill('1');
  await preview(page); await save(page);

  const records = (await (await page.request.get(base + '/activities')).json()).items;
  expect(records).toHaveLength(4);
  expect(records.map((record: { category: string }) => record.category).sort()).toEqual(['electricity', 'food', 'travel', 'waste']);
  const electricity = records.find((record: { category: string }) => record.category === 'electricity');
  const evidence = await (await page.request.get(base + '/calculations/' + electricity.calculation_id)).json();
  expect(evidence.calculation.energy_conversion.kwh).toBe('6.000000');
  await navigate(page, 'Overview');
  const summary = await (await page.request.get(base + '/summary?period=week')).json();
  await expect(page.locator('.stat-featured .stat-number')).toContainText(summary.summary.display_total_kg_co2e);
  await navigate(page, 'Activity history');
  await expect(page.locator('.activity-list article')).toHaveCount(4);
});

test('a lost save response restores a locked operation and retries without duplication', async ({ page }, info) => {
  const base = await start(page);
  const keys: string[] = [];
  let lost = false;
  await page.route('**/activities', async route => {
    if (route.request().method() !== 'POST') { await route.continue(); return; }
    keys.push(route.request().headers()['idempotency-key']);
    const response = await route.fetch();
    if (!lost) { lost = true; await route.abort('failed'); return; }
    await route.fulfill({ response });
  });
  await page.getByLabel('Travel mode').selectOption('bus');
  await page.getByLabel('Distance travelled (km)').fill('12');
  await preview(page);
  await page.getByRole('button', { name: 'Save activity', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry save safely' })).toBeVisible();
  expect((await (await page.request.get(base + '/activities')).json()).items).toHaveLength(1);
  await expect(page.getByLabel('Distance travelled (km)')).toBeDisabled();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Retry save safely' })).toBeVisible();
  await expect(page.getByLabel('Distance travelled (km)')).toBeDisabled();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/recovery-${info.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'Retry save safely' }).click();
  await expect(page.getByText('Activity saved', { exact: true })).toBeVisible();
  expect(keys).toHaveLength(2); expect(keys[0]).toBe(keys[1]);
  expect((await (await page.request.get(base + '/activities')).json()).items).toHaveLength(1);
});

test('incomplete appliances and future dates create no guessed calculation', async ({ page }) => {
  await start(page);
  let calculations = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/calculations')) calculations++; });
  await page.getByRole('button', { name: 'Electricity', exact: true }).click();
  await page.getByRole('radio', { name: 'Appliance power and time' }).check();
  await page.getByLabel('Hours used').fill('4');
  await page.getByRole('button', { name: 'Preview estimate' }).click();
  await expect(page.getByRole('alert')).toContainText('Check the highlighted fields');
  expect(calculations).toBe(0);
  await page.getByLabel('Reference grid').selectOption('UK');
  await page.getByLabel('Power measurement').selectOption('rated');
  await page.getByLabel('Electrical input power (kW)').fill('1.5');
  await page.getByRole('button', { name: 'Preview estimate' }).click();
  await expect(page.getByLabel('Duty cycle (fraction)')).toHaveAttribute('aria-invalid', 'true');
  expect(calculations).toBe(0);
  await page.getByLabel('Duty cycle (fraction)').fill('0.5');
  await page.getByLabel('Activity date').fill('2999-01-01');
  await page.getByRole('button', { name: 'Preview estimate' }).click();
  await expect(page.getByLabel('Activity date')).toHaveAttribute('aria-invalid', 'true');
  expect(calculations).toBe(0);
});

test('preview evidence survives reload and car occupancy stays explicit', async ({ page }, info) => {
  await start(page);
  await page.getByLabel('Travel mode').selectOption('car_petrol');
  await page.getByLabel('Distance travelled (km)').fill('12');
  await page.getByRole('button', { name: 'Preview estimate' }).click();
  await expect(page.getByLabel('People in the car')).toHaveAttribute('aria-invalid', 'true');
  await page.getByLabel('People in the car').fill('2');
  await preview(page);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Save activity', exact: true })).toBeVisible();
  await page.getByText('Sources and assumptions', { exact: true }).click();
  await expect(page.getByText('Calculation: 12 * 0.16272 / 2', { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/activity-preview-${info.project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});
