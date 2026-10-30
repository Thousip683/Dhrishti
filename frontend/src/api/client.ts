import type { ErrorResponse } from './schema';

let csrfToken = '';
export function setCsrfToken(value: string) { csrfToken = value; }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string,
    public requestId = '', public retryable = false,
    public fields: Array<{ field: string; reason: string }> = []) { super(message); }
}

export type ApiOptions = Omit<RequestInit, 'body'> & { body?: unknown; mutationKey?: string };

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { body, mutationKey, ...init } = options;
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (body !== undefined) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  if (mutationKey) headers.set('Idempotency-Key', mutationKey);
  let response: Response;
  try {
    response = await fetch(path, { ...init, method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach Carbon Coach. Your unsaved changes are still here.', '', true);
  }
  if (!response.ok) {
    const data: ErrorResponse | null = await response.json().catch(() => null);
    const error = new ApiError(response.status, data?.error?.code ?? 'HTTP_ERROR', data?.error?.message ?? 'The request could not be completed.', data?.request_id ?? response.headers.get('X-Request-ID') ?? '', data?.error?.retryable ?? response.status >= 500, data?.error?.field_errors ?? []);
    if (response.status === 401 || (response.status === 404 && path === '/api/v1/browser/session')) window.dispatchEvent(new Event('cc:expired'));
    throw error;
  }
  const expires = response.headers.get('X-Session-Expires-At');
  if (expires) window.dispatchEvent(new CustomEvent('cc:expiry', { detail: expires }));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function savedDraft(key: string, fallback: string): string {
  try { return sessionStorage.getItem(`cc:${key}`) ?? fallback; } catch { return fallback; }
}
export function saveDraft(key: string, value: string) {
  try { sessionStorage.setItem(`cc:${key}`, value); } catch { /* Form remains usable without browser storage. */ }
}
export function clearDrafts() {
  try { Object.keys(sessionStorage).filter(key => key.startsWith('cc:')).forEach(key => sessionStorage.removeItem(key)); } catch { /* No persistent credentials are stored here. */ }
}
