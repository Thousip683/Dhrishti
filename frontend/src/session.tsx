import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { BrowserSessionResponse } from './api/schema';
import { api, ApiError, clearDrafts, setCsrfToken } from './api/client';

export const SESSION_KEY = ['browser-session'];
type SessionContext = {
  session: BrowserSessionResponse | null;
  loading: boolean;
  error: Error | null;
  notice: string;
  refresh: () => void;
  accept: (session: BrowserSessionResponse) => void;
  erase: () => Promise<void>;
};
const Context = createContext<SessionContext | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const [notice, setNotice] = useState('');
  const query = useQuery({ queryKey: SESSION_KEY, retry: false, refetchOnWindowFocus: true,
    queryFn: async ({ signal }) => {
      try { return await api<BrowserSessionResponse>('/api/v1/browser/session', { signal }); }
      catch (error) { if (error instanceof ApiError && [401, 404].includes(error.status)) return null; throw error; }
    },
  });
  const session = query.data ?? null;
  useEffect(() => { setCsrfToken(session?.csrf_token ?? ''); }, [session]);
  useEffect(() => {
    const renewed = (event: Event) => {
      const expires = (event as CustomEvent<string>).detail;
      if (!Number.isFinite(Date.parse(expires))) return;
      cache.setQueryData<BrowserSessionResponse | null>(SESSION_KEY, current => current ? { ...current, expires_at: expires } : current);
    };
    window.addEventListener('cc:expiry', renewed);
    return () => window.removeEventListener('cc:expiry', renewed);
  }, [cache]);
  const reset = async (message: string) => {
    await cache.cancelQueries();
    cache.clear();
    clearDrafts();
    setCsrfToken('');
    cache.setQueryData(SESSION_KEY, null);
    setNotice(message);
  };
  useEffect(() => {
    if (!session) return;
    const expire = () => { void reset('Your session expired. Start a new one to continue.'); };
    window.addEventListener('cc:expired', expire);
    const remaining = new Date(session.expires_at).getTime() - Date.now();
    const timeout = window.setTimeout(expire, Math.max(0, remaining));
    return () => { window.removeEventListener('cc:expired', expire); window.clearTimeout(timeout); };
  }, [session?.session_id, session?.expires_at]);
  return <Context.Provider value={{ session, loading: query.isPending, error: query.error, notice,
    refresh: () => { void query.refetch(); },
    accept: value => { setCsrfToken(value.csrf_token); cache.setQueryData(SESSION_KEY, value); setNotice(''); },
    erase: async () => { await api('/api/v1/browser/session', { method: 'DELETE' }); await reset('Your session and its activities have been erased.'); },
  }}>{children}</Context.Provider>;
}

export function useSession() { const value = useContext(Context); if (!value) throw new Error('SessionProvider is required'); return value; }
