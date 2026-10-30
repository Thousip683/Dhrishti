import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowDownLeft, ArrowRight, BookOpen, CalendarDays, Check, CheckCircle2, ChevronRight, Clock3, ExternalLink, Footprints, History, LayoutDashboard, Leaf, Lightbulb, Menu, MessageCircle, Plus, Settings as SettingsIcon, ShieldCheck, Sprout, Trash2, WifiOff, X } from 'lucide-react';
import { api, ApiError, savedDraft, saveDraft, setCsrfToken } from './api/client';
import type { ActivityListResponse, BrowserBootstrapResponse, BrowserSessionResponse, FactorListResponse, SummaryResponse } from './api/schema';
import { useSession } from './session';
import { Brand, ErrorNotice, Loading, PageHeading } from './components';
import { ActivityLog } from './ActivityLog';
import { Chat } from './Chat';

const nav = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/log', label: 'Log activity', icon: Plus },
  { to: '/activities', label: 'Activity history', icon: History },
  { to: '/chat', label: 'Chat with coach', icon: MessageCircle },
  { to: '/insights', label: 'Insights', icon: Lightbulb },
  { to: '/sources', label: 'Our sources', icon: BookOpen },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
];
const zones = ['Asia/Kolkata', 'UTC', 'Europe/London', 'America/New_York', 'Asia/Singapore'];

function localTimezone() {
  const value = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return value === 'Asia/Calcutta' ? 'Asia/Kolkata' : value;
}

export function App() {
  const { session, loading, error, refresh } = useSession();
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update); window.addEventListener('offline', update);
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); };
  }, []);
  return <>
    <a className="skip-link" href="#main-content">Skip to main content</a>
    {!online && <div className="offline-banner" role="status"><WifiOff size={16} />You’re offline. Unsaved form changes stay on this device until you reconnect.</div>}
    {loading ? <main id="main-content" className="startup"><Brand /><Loading /></main> :
      error ? <main id="main-content" className="startup"><Brand /><h1>Let’s reconnect</h1><p>Your session may still be available. Try connecting again before starting over.</p><ErrorNotice error={error} retry={refresh} /></main> :
        session ? <Shell /> : <Welcome />}
  </>;
}

function Welcome() {
  const { accept, notice } = useSession();
  const [timezone, setTimezone] = useState(() => savedDraft('welcome-timezone', localTimezone()));
  const [mutationKey] = useState(() => {
    return savedDraft('creation-key', crypto.randomUUID());
  });
  const create = useMutation({ mutationFn: async () => {
    saveDraft('creation-key', mutationKey);
    const bootstrap = await api<BrowserBootstrapResponse>('/api/v1/browser/bootstrap');
    setCsrfToken(bootstrap.csrf_token);
    return api<BrowserSessionResponse>('/api/v1/browser/session', { method: 'POST', mutationKey, body: { timezone, region: 'UK', locale: 'en' } });
  }, onSuccess: value => { accept(value); } });
  function submit(event: FormEvent) { event.preventDefault(); create.mutate(); }
  return <main id="main-content" className="welcome">
    <section className="welcome-story"><Brand light /><div className="welcome-copy"><p className="eyebrow">A LITTLE AWARENESS GOES A LONG WAY</p><h1>Understand your<br />everyday impact.</h1><p>A clear place for the things you log, the estimates behind them, and the changes you can explore.</p><div className="welcome-leaf" aria-hidden="true"><Sprout size={140} strokeWidth={0.65} /><span className="orbit orbit-one" /><span className="orbit orbit-two" /></div></div><p className="welcome-foot">CARBON COACH <span>DEVFEST 2026</span></p></section>
    <section className="welcome-form"><div className="onboarding"><span className="icon-tile"><Leaf size={24} /></span><p className="eyebrow">LET’S GET STARTED</p><h2>A fresh perspective.<br />A session of your own.</h2><p>Start without an account. Your browser keeps a private session, so you can return to your logged activities.</p>
      {notice && <div className="notice" role="status"><CheckCircle2 size={18} />{notice}</div>}
      <form onSubmit={submit}>
        <label htmlFor="welcome-timezone">Your timezone</label><input id="welcome-timezone" list="timezones" value={timezone} onChange={e => { setTimezone(e.target.value); saveDraft('welcome-timezone', e.target.value); }} required disabled={create.isPending} aria-describedby="timezone-help" />
        <datalist id="timezones">{zones.map(zone => <option key={zone} value={zone} />)}</datalist><small id="timezone-help">Used to decide which day your activities belong to.</small>
        <label htmlFor="reference">Reference dataset</label><select id="reference" disabled><option>UK reference · Global food averages</option></select><small>These estimates are not India-specific. Each result keeps its source and assumptions.</small>
        {create.error && <ErrorNotice error={create.error} />}
        <button className="button button-primary button-full" disabled={create.isPending} type="submit">{create.isPending ? 'Creating your session…' : 'Start my session'}{!create.isPending && <ArrowRight size={18} />}</button>
      </form><p className="privacy-note"><ShieldCheck size={16} />No name, email or location tracking required.</p><p className="fine-print">Your session expires after a day of inactivity. You can erase it at any time.</p>
    </div></section>
  </main>;
}

function Shell() {
  const { session } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => matchMedia('(max-width: 760px)').matches);
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  useEffect(() => { setMenuOpen(false); window.scrollTo(0, 0); main.current?.focus({ preventScroll: true }); }, [location.pathname]);
  useEffect(() => {
    const media = matchMedia('(max-width: 760px)');
    const update = () => setIsMobile(media.matches);
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false); };
    media.addEventListener('change', update); window.addEventListener('keydown', escape);
    return () => { media.removeEventListener('change', update); window.removeEventListener('keydown', escape); };
  }, []);
  const today = new Intl.DateTimeFormat('en', { day: 'numeric', month: 'long', year: 'numeric', timeZone: session!.timezone }).format(new Date());
  const current = nav.find(item => location.pathname.startsWith(item.to))?.label ?? 'Carbon Coach';
  return <div className="app-shell">
    <header className="mobile-header"><Brand /><button className="icon-button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="sidebar" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />}</button></header>
    {menuOpen && <button className="menu-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <aside id="sidebar" aria-hidden={isMobile && !menuOpen} inert={isMobile && !menuOpen} className={`sidebar ${menuOpen ? 'is-open' : ''}`}><Brand light /><div className="workspace-label">YOUR SPACE</div><nav aria-label="Main navigation">{nav.map(item => <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={19} strokeWidth={1.65} /><span>{item.label}</span>{item.to === '/log' && <span className="nav-add" aria-hidden="true">+</span>}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><Sprout size={25} strokeWidth={1.3} /><p>Start with what you know.<br /><span>Every log adds a little clarity.</span></p></div><Link className="session-badge" to="/settings"><span className="avatar"><Leaf size={18} /></span><span>Your private session<small>{session?.storage_mode === 'database' ? 'Saved on this server' : 'Temporary memory storage'}</small></span><ChevronRight size={15} /></Link></div>
    </aside>
    <div className="app-body"><header className="topbar"><div>My space <ChevronRight size={13} /><span>{current}</span></div><span className="reference-badge"><span className="status-dot" />UK reference data</span></header>
      <main id="main-content" className="main" tabIndex={-1} ref={main}><div className="page-date"><CalendarDays size={14} />{today}</div>
        {session?.storage_mode === 'memory' && <div className="notice">This server is using temporary memory. A restart will erase its sessions.</div>}
        <Routes><Route path="/dashboard" element={<Overview />} /><Route path="/log" element={<ActivityLog />} /><Route path="/activities" element={<ActivityHistory />} /><Route path="/insights" element={<InsightsPreview />} /><Route path="/sources" element={<Sources />} /><Route path="/settings" element={<SettingsPage />} /><Route path="/chat" element={<Chat />} /><Route path="/" element={<Navigate to="/dashboard" replace />} /><Route path="/welcome" element={<Navigate to="/dashboard" replace />} /><Route path="*" element={<NotFound />} /></Routes>
        <footer className="page-footer"><span><Leaf size={13} />Carbon Coach</span><span>Estimates with context. Progress at your pace.</span></footer>
      </main>
    </div>
  </div>;
}

function Overview() {
  const { session } = useSession();
  const summary = useQuery({ queryKey: ['summary', session!.session_id, 'week'], queryFn: ({ signal }) => api<SummaryResponse>(`/api/v1/sessions/${session!.session_id}/summary?period=week`, { signal }) });
  const data = summary.data?.summary;
  return <><PageHeading eyebrow="YOUR OVERVIEW" title="Your footprint at a glance">A little clarity on the activities you’ve recorded this week.</PageHeading>
    {summary.error ? <ErrorNotice error={summary.error} retry={() => { void summary.refetch(); }} /> : !data ? <Loading label="Fetching your logged activities…" /> : <>
      <section className="stat-grid" aria-label="Logged activity statistics"><article className="stat-card stat-featured"><div className="stat-label">This week’s logged estimate <Leaf size={18} /></div><p className="stat-number">{data.display_total_kg_co2e}<span>kg CO₂e</span></p><small>{data.activity_count ? 'Based on the activities you saved' : 'No activities recorded yet'}</small></article><article className="stat-card"><div className="stat-label">Activities recorded <Footprints size={18} /></div><p className="stat-number">{data.activity_count}</p><small>Travel, energy, food and waste</small></article><article className="stat-card"><div className="stat-label">Days with entries <CalendarDays size={18} /></div><p className="stat-number">{data.logged_day_count}</p><small>Unlogged days are unknown</small></article></section>
      <div className="overview-grid"><section className="panel journey-panel"><div className="panel-heading"><h2>{data.activity_count ? 'Your record is taking shape' : 'Your story starts with a first entry'}</h2><span className="soft-tag">GETTING STARTED</span></div><div className="journey-illustration" aria-hidden="true"><span /><span /><span /><Sprout size={76} strokeWidth={1} /></div><p>{data.activity_count ? 'Your saved records are ready to review. Open your history to see the details behind each estimate.' : 'A bus ride. A meal. The electricity you used. There’s no need to capture everything at once.'}</p><Link className="button button-primary" to={data.activity_count ? '/activities' : '/log'}>{data.activity_count ? 'Review my activities' : 'Explore activity logging'}<ArrowRight size={16} /></Link><div className="coverage-note"><Clock3 size={14} /><span>{data.coverage_note}</span></div></section>
      <aside className="panel source-panel"><span className="icon-tile"><BookOpen size={22} /></span><p className="eyebrow">KNOW WHAT’S BEHIND THE NUMBER</p><h2>Clear sources.<br />Honest estimates.</h2><p>Our current dataset uses UK references and global food averages. Each estimate has a scope, a source and assumptions.</p><Link className="text-link" to="/sources">Meet the sources <ArrowRight size={15} /></Link><div className="source-facts"><p><Check size={15} />Published emission factors</p><p><Check size={15} />Transparent regional limits</p><p><Check size={15} />Your data stays in your session</p></div></aside></div>
    </>}</>;
}

function ActivityHistory() {
  const { session } = useSession();
  const query = useQuery({ queryKey: ['activities', session!.session_id], queryFn: ({ signal }) => api<ActivityListResponse>(`/api/v1/sessions/${session!.session_id}/activities`, { signal }) });
  return <><PageHeading eyebrow="YOUR RECORD" title="One activity at a time">The activities saved in this browser session.</PageHeading>{query.isPending ? <Loading label="Loading saved records…" /> : query.error ? <ErrorNotice error={query.error} retry={() => { void query.refetch(); }} /> : !query.data?.items.length ? <EmptyState icon="history" title="A clean page, ready for you" text="You haven’t saved any activities in this session yet. Your recorded activities will appear here." action={<Link className="button button-primary" to="/log">Explore logging <ArrowRight size={16} /></Link>} /> : <section className="panel activity-list">{query.data.items.map(item => <article key={item.id}><span className="icon-tile"><Footprints size={20} /></span><div><h2>{item.category}</h2><p>{item.note || 'Saved activity'} · {item.activity_date}</p></div><strong>{item.kg_co2e}<small>kg CO₂e</small></strong></article>)}</section>}</>;
}

function InsightsPreview() {
  return <><PageHeading eyebrow="A FRESH PERSPECTIVE" title="Clarity before comparison">Understand your own record before looking at what could change.</PageHeading><EmptyState icon="insights" title="Insights need a little context" text="The comparison and recommendations view is still being prepared. You can already inspect the sources behind your estimates." action={<Link className="button button-secondary" to="/sources">Explore our sources <ArrowRight size={16} /></Link>} /></>;
}

function Sources() {
  const query = useQuery({ queryKey: ['factors'], queryFn: ({ signal }) => api<FactorListResponse>('/api/v1/factors', { signal }) });
  return <><PageHeading eyebrow="TRANSPARENCY FIRST" title="Every estimate has a source">See the factors we use, where they apply, and what they leave out.</PageHeading><div className="notice"><BookOpen size={19} />UK reference factors are not India-specific measurements. Food factors are global averages.</div>{query.isPending ? <Loading label="Loading the source registry…" /> : query.error ? <ErrorNotice error={query.error} retry={() => { void query.refetch(); }} /> : <section className="source-list">{query.data?.items.map(factor => <details className="panel source-detail" key={factor.id}><summary><span className="icon-tile"><BookOpen size={19} /></span><span><strong>{factor.id.replaceAll('_', ' ')}</strong><small>{factor.geography} · {factor.category}</small></span><ChevronRight size={18} /></summary><div className="source-content"><p><strong>{factor.value} kg CO₂e / {factor.denominator_unit}</strong></p><p>{factor.source_publisher} · {factor.version}</p><p>{factor.limitations}</p><dl><dt>Boundary</dt><dd>{factor.boundary.replaceAll('_', ' ')}</dd><dt>Source record</dt><dd>{factor.source_locator}</dd></dl>{factor.source_url.startsWith('https://') && <a className="text-link" href={factor.source_url} target="_blank" rel="noreferrer">Open original source <ExternalLink size={14} /></a>}</div></details>)}</section>}</>;
}

function SettingsPage() {
  const { session, accept, erase } = useSession();
  const [timezone, setTimezone] = useState(() => savedDraft(`timezone:${session!.session_id}`, session!.timezone));
  const key = useRef(crypto.randomUUID());
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const update = useMutation({ mutationFn: () => api<BrowserSessionResponse>('/api/v1/browser/session', { method: 'PATCH', mutationKey: key.current, body: { timezone } }), onSuccess: value => { accept(value); saveDraft(`timezone:${value.session_id}`, value.timezone); key.current = crypto.randomUUID(); setSaved(true); } });
  const remove = useMutation({ mutationFn: erase, onError: () => { setConfirm(false); } });
  useEffect(() => { if (confirm) dialog.current?.showModal(); else dialog.current?.close(); }, [confirm]);
  function submit(event: FormEvent) { event.preventDefault(); update.mutate(); }
  return <><PageHeading eyebrow="YOUR SESSION" title="A space you control">Choose how dates work, understand storage, or clear your record.</PageHeading><section className="panel settings-panel"><div className="panel-heading"><h2>Session preferences</h2><span className="soft-tag">PRIVATE BROWSER SESSION</span></div><form onSubmit={submit}><label htmlFor="settings-timezone">Timezone</label><input id="settings-timezone" list="settings-zones" value={timezone} onChange={event => { setTimezone(event.target.value); saveDraft(`timezone:${session!.session_id}`, event.target.value); key.current = crypto.randomUUID(); setSaved(false); }} required disabled={update.isPending || remove.isPending} aria-describedby="settings-timezone-help" /><datalist id="settings-zones">{zones.map(zone => <option key={zone} value={zone} />)}</datalist><small id="settings-timezone-help">Changing this affects future relative dates. Saved activity dates stay unchanged.</small>{update.error && <ErrorNotice error={update.error} />}<div className="form-actions"><button className="button button-primary" disabled={update.isPending || remove.isPending}>{update.isPending ? 'Saving…' : 'Save preferences'}</button>{saved && <span className="saved-message" role="status"><CheckCircle2 size={16} />Preferences saved</span>}</div></form><div className="settings-facts"><div><span>Storage</span><strong>{session!.storage_mode === 'database' ? 'Durable server storage' : 'Temporary memory'}</strong></div><div><span>Expiry without activity</span><strong><time dateTime={session!.expires_at}>{new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short", timeZone: session!.timezone }).format(new Date(session!.expires_at))}</time></strong></div><div><span>Reference region</span><strong>{session!.region} reference · Global food</strong></div><div><span>Chat connection</span><strong>{session!.chat_mode === 'mock' ? 'Development mock' : session!.chat_mode === 'configured' ? 'Configured · availability not verified' : 'Not configured'}</strong></div></div></section>
    <section className="panel erase-panel"><div><h2>Leave a clean slate</h2><p>Erase this session, its activities and saved calculations. This cannot be undone.</p></div><button className="button button-danger" onClick={() => setConfirm(true)} disabled={update.isPending || remove.isPending}><Trash2 size={16} />Erase my session</button>{remove.error && <ErrorNotice error={remove.error} />}</section>
    <dialog ref={dialog} className="confirm-dialog" onCancel={event => { if (remove.isPending) event.preventDefault(); else setConfirm(false); }} onClose={() => setConfirm(false)} aria-labelledby="erase-title" aria-describedby="erase-description"><span className="icon-tile danger-tile"><Trash2 size={24} /></span><h2 id="erase-title">Erase your session?</h2><p id="erase-description">Your activities, calculations and session will be removed from this server. You’ll return to the welcome screen.</p><div className="dialog-actions"><button autoFocus className="button button-secondary" onClick={() => setConfirm(false)} disabled={remove.isPending}>Keep my session</button><button className="button button-danger" onClick={() => remove.mutate()} disabled={remove.isPending}>{remove.isPending ? 'Erasing…' : 'Yes, erase session'}</button></div></dialog>
  </>;
}

function EmptyState({ title, text, action, icon }: { title: string; text: string; action?: React.ReactNode; icon: 'history' | 'insights' }) {
  return <section className="panel empty-state"><span className="empty-icon">{icon === 'history' ? <History size={43} strokeWidth={1} /> : <Lightbulb size={43} strokeWidth={1} />}</span><h2>{title}</h2><p>{text}</p>{action}</section>;
}
function NotFound() { return <><PageHeading eyebrow="A DIFFERENT PATH" title="That page isn’t here">Return to your overview to find your way around.</PageHeading><Link className="button button-primary" to="/dashboard">Back to overview <ArrowRight size={16} /></Link></>; }
