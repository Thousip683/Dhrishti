import { describe, expect, it, vi } from 'vitest';
import { api, ApiError, clearDrafts, savedDraft, saveDraft, setCsrfToken } from './client';

describe('API client', () => {
  it('uses same-origin cookies, CSRF and the supplied retry key without browser bearer storage', async () => {
    const fetch = vi.spyOn(window, 'fetch').mockResolvedValue(new Response(JSON.stringify({ status: 'success' }), { status: 200 }));
    setCsrfToken('csrf-value');
    await api('/api/v1/browser/session', { method: 'PATCH', mutationKey: 'same-key', body: { timezone: 'UTC' } });
    const options = fetch.mock.calls[0][1]!;
    expect(options.credentials).toBe('same-origin');
    const headers = options.headers as Headers;
    expect(headers.get('X-CSRF-Token')).toBe('csrf-value');
    expect(headers.get('Idempotency-Key')).toBe('same-key');
    expect(headers.has('Authorization')).toBe(false);
  });
  it('retains drafts after a failed network request', async () => {
    saveDraft('timezone:session', 'Asia/Kolkata');
    vi.spyOn(window, 'fetch').mockRejectedValue(new TypeError('offline'));
    await expect(api('/api/v1/browser/session')).rejects.toMatchObject({ code: 'NETWORK_ERROR', retryable: true });
    expect(savedDraft('timezone:session', '')).toBe('Asia/Kolkata');
  });
  it('normalizes server errors and request IDs', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response(JSON.stringify({ request_id: 'ref-1', status: 'error', error: { code: 'CSRF_REJECTED', message: 'Refresh your session.', retryable: false } }), { status: 403 }));
    await expect(api('/api/v1/browser/session')).rejects.toMatchObject({ code: 'CSRF_REJECTED', requestId: 'ref-1', status: 403 });
  });
  it('does not expire a valid session when a record is missing', async () => {
    const listener = vi.fn(); window.addEventListener('cc:expired', listener);
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response('{}', { status: 404 }));
    await expect(api('/api/v1/sessions/own/activities/missing')).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled(); window.removeEventListener('cc:expired', listener);
  });
  it('clears only application drafts on erasure', () => {
    sessionStorage.setItem('another-app', 'keep'); saveDraft('draft', 'remove'); clearDrafts();
    expect(sessionStorage.getItem('another-app')).toBe('keep'); expect(savedDraft('draft', 'empty')).toBe('empty');
  });
});
