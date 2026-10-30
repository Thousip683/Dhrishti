import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SessionProvider } from './session';
import { App } from './App';
import './styles.css';
import './activity.css';
import './chat.css';

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: false } } });
createRoot(document.getElementById('root')!).render(
  <React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><SessionProvider><App /></SessionProvider></BrowserRouter></QueryClientProvider></React.StrictMode>,
);
