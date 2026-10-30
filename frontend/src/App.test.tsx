import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { SessionProvider } from './session';

function renderApp() { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter><SessionProvider><App /></SessionProvider></MemoryRouter></QueryClientProvider>); }
describe('session entry', () => {
  it('shows welcome after an unauthenticated restore without inventing a session', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Start a session.', retryable: false } }), { status: 401 }));
    renderApp();
    expect(await screen.findByRole('button', { name: 'Start my session' })).toBeInTheDocument();
    expect(screen.getByLabelText('Your timezone')).toBeInTheDocument();
  });
  it('offers retry instead of creating another session when the server cannot be reached', async () => {
    vi.spyOn(window, 'fetch').mockRejectedValue(new TypeError('offline')); renderApp();
    expect(await screen.findByText('Let’s reconnect')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start my session' })).not.toBeInTheDocument();
  });
  it('preserves an onboarding timezone draft after reload', async () => {
    sessionStorage.setItem('cc:welcome-timezone', 'UTC');
    vi.spyOn(window, 'fetch').mockImplementation(async () => new Response('{}', { status: 401 }));
    renderApp();
    expect(await screen.findByLabelText('Your timezone')).toHaveValue('UTC');
    await userEvent.clear(screen.getByLabelText('Your timezone')); await userEvent.type(screen.getByLabelText('Your timezone'), 'Europe/London');
    expect(sessionStorage.getItem('cc:welcome-timezone')).toBe('Europe/London');
  });
});
