import { expect, test, type Page } from '@playwright/test';

async function start(page: Page) {
  await page.goto('/');
  await page.getByLabel('Your timezone').fill('Asia/Kolkata');
  await page.getByRole('button', { name: 'Start my session' }).click();
  await expect(page.getByRole('heading', { name: 'Your footprint at a glance' })).toBeVisible();
}
async function navigate(page: Page, label: string) {
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('navigation').getByRole('link', { name: label, exact: true }).click();
}

test('create, refresh, navigate, update timezone and erase a browser session', async ({ page }, info) => {
  await start(page);
  const initial = await page.request.get('/api/v1/browser/session');
  const session = await initial.json();
  expect(session.chat_mode).toBe('mock');
  await page.screenshot({ path: `test-results/overview-${info.project.name}.png`, fullPage: true });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Your footprint at a glance' })).toBeVisible();
  expect((await (await page.request.get('/api/v1/browser/session')).json()).session_id).toBe(session.session_id);
  await navigate(page, 'Our sources');
  await expect(page.getByRole('heading', { name: 'Every estimate has a source' })).toBeVisible();
  await page.getByText('car diesel', { exact: true }).click();
  await expect(page.getByRole('link', { name: 'Open original source' }).first()).toBeVisible();
  await navigate(page, 'Settings');
  await page.getByLabel('Timezone', { exact: true }).fill('UTC');
  await page.getByRole('button', { name: 'Save preferences' }).click();
  await expect(page.getByText('Preferences saved', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Timezone', { exact: true })).toHaveValue('UTC');
  await page.screenshot({ path: `test-results/settings-${info.project.name}.png`, fullPage: true });
  expect((await (await page.request.get('/api/v1/browser/session')).json()).timezone).toBe('UTC');
  await page.getByRole('button', { name: 'Erase my session' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Keep my session' })).toBeFocused();
  await page.getByRole('button', { name: 'Yes, erase session' }).click();
  await expect(page.getByRole('button', { name: 'Start my session' })).toBeVisible();
  await page.screenshot({ path: `test-results/welcome-${info.project.name}.png`, fullPage: true });
  expect((await page.request.get('/api/v1/browser/session')).status()).toBe(401);
  expect(await page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('cc:')))).toEqual([]);
});

test('failed onboarding keeps its draft and uses the same retry key', async ({ page }) => {
  let fail = true;
  const keys: string[] = [];
  await page.route('**/api/v1/browser/session', async route => {
    if (route.request().method() === 'POST') {
      keys.push(route.request().headers()['idempotency-key']);
      if (fail) { fail = false; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ request_id: 'network-test', status: 'error', error: { code: 'STORAGE_UNAVAILABLE', message: 'Please retry this request.', retryable: true } }) }); return; }
    }
    await route.continue();
  });
  await page.goto('/');
  await page.getByLabel('Your timezone').fill('Europe/London');
  await page.getByRole('button', { name: 'Start my session' }).click();
  await expect(page.getByRole('alert')).toContainText('Please retry');
  await expect(page.getByLabel('Your timezone')).toHaveValue('Europe/London');
  await page.reload();
  await expect(page.getByLabel('Your timezone')).toHaveValue('Europe/London');
  await page.getByRole('button', { name: 'Start my session' }).click();
  await expect(page.getByRole('heading', { name: 'Your footprint at a glance' })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

test('cookie privacy, CSRF rejection and responsive navigation', async ({ page, context }, info) => {
  await start(page);
  const cookies = await context.cookies();
  expect(cookies.find(cookie => cookie.name === 'cc_session')?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain('cc_session');
  const reject = await page.request.patch('/api/v1/browser/session', { data: { timezone: 'UTC' }, headers: { Origin: 'http://127.0.0.1:8012' } });
  expect(reject.status()).toBe(403);
  if (info.project.name === 'mobile') {
    await expect(page.getByRole('navigation')).toHaveCount(0);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await expect(page.getByRole('navigation')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('navigation')).toHaveCount(0);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
