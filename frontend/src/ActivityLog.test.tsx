import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fixture from './fixtures/application.json';
import { ActivityLog } from './ActivityLog';

vi.mock('./session', () => ({ SESSION_KEY: ['browser-session'], useSession: () => ({ session: { session_id: 'form-session', timezone: 'Asia/Kolkata' } }) }));

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 30000 }, mutations: { retry: false } } });
  client.setQueryData(['browser-session'], { session_id: 'form-session', timezone: 'Asia/Kolkata' });
  return render(<QueryClientProvider client={client}><MemoryRouter><ActivityLog /></MemoryRouter></QueryClientProvider>);
}
const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });
async function previewTravel() {
  await userEvent.selectOptions(await screen.findByLabelText('Travel mode'), 'bus');
  await userEvent.type(screen.getByLabelText('Distance travelled (km)'), '12');
  await userEvent.click(screen.getByRole('button', { name: 'Preview estimate' }));
  await screen.findByRole('button', { name: 'Save activity' });
}

describe('preview and save lifecycle', () => {
  it('removes the save action immediately when previewed inputs change', async () => {
    const fetch = vi.spyOn(window, 'fetch').mockImplementation(async (url, init) => String(url).endsWith('/capabilities') ? response(fixture.capabilities) : response(fixture.calculation));
    renderForm(); await previewTravel();
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/activities'))).toBe(false);
    await userEvent.clear(screen.getByLabelText('Distance travelled (km)'));
    await userEvent.type(screen.getByLabelText('Distance travelled (km)'), '8');
    expect(screen.queryByRole('button', { name: 'Save activity' })).not.toBeInTheDocument();
  });
  it('restores an unconfirmed save and retries the original operation exactly once', async () => {
    const keys: string[] = [];
    let attempts = 0;
    vi.spyOn(window, 'fetch').mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.endsWith('/capabilities')) return response(fixture.capabilities);
      if (path.endsWith('/activities')) {
        keys.push((init!.headers as Headers).get('Idempotency-Key')!);
        attempts++;
        if (attempts === 1) throw new TypeError('Response was lost');
        return response(fixture.activity);
      }
      return response(fixture.calculation);
    });
    const first = renderForm(); await previewTravel();
    await userEvent.click(screen.getByRole('button', { name: 'Save activity' }));
    await screen.findByRole('button', { name: 'Retry save safely' });
    expect(screen.getByLabelText('Distance travelled (km)')).toBeDisabled();
    first.unmount(); renderForm();
    await userEvent.click(await screen.findByRole('button', { name: 'Retry save safely' }));
    await screen.findByText('Activity saved', { exact: true });
    expect(keys).toHaveLength(2); expect(keys[0]).toBe(keys[1]);
  });
});
