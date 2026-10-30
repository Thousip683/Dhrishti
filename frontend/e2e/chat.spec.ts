import { expect, test } from '@playwright/test';

test('chat uses the same authenticated session and restores its transcript', async ({ page },info) => {
  await page.goto('/');
  await page.getByRole('button',{name:'Start my session'}).click();
  await expect(page.getByRole('heading',{name:'Your footprint at a glance'})).toBeVisible();
  if(await page.getByRole('button',{name:'Open navigation'}).isVisible()) await page.getByRole('button',{name:'Open navigation'}).click();
  await page.getByRole('navigation').getByRole('link',{name:'Chat with coach',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Talk through your everyday impact'})).toBeVisible();
  await page.getByLabel('Reply language').selectOption('hi');
  await page.getByLabel('Your message').fill('नमस्ते');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.getByRole('log')).toContainText('Mock chat adapter');
  await expect(page.getByLabel('Your message')).toHaveValue('');
  await page.reload();
  await expect(page.getByRole('log')).toContainText('नमस्ते');
  await expect(page.getByRole('log')).toContainText('Mock chat adapter');
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:`test-results/chat-${info.project.name}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false);
});
