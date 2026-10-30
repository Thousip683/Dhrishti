import { AlertCircle, ArrowRight, LoaderCircle, Leaf } from 'lucide-react';
import type { ReactNode } from 'react';
import { ApiError } from './api/client';

export function Brand({ light = false }: { light?: boolean }) {
  return <div className={`brand ${light ? 'brand-light' : ''}`}><span className="brand-mark"><Leaf size={23} strokeWidth={1.6} /></span><span>carbon<span className="brand-weight">coach</span><small>SMALL STEPS. CLEARER IMPACT.</small></span></div>;
}
export function Loading({ label = 'Loading your session…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} />{label}</div>;
}
export function ErrorNotice({ error, retry }: { error: Error; retry?: () => void }) {
  return <div className="error-notice" role="alert"><AlertCircle size={20} /><div><strong>{error.message}</strong>{error instanceof ApiError && error.requestId && <small>Request reference: {error.requestId}</small>}{retry && <button className="text-button" onClick={retry}>Try again <ArrowRight size={14} /></button>}</div></div>;
}
export function PageHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <div className="page-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{children && <p className="lede">{children}</p>}</div>;
}
