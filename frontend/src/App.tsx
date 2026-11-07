import { useEffect, useRef, useState } from 'react';
import type { Alert } from './marginguard-api';
import { api, usePoll } from './mg/client';
import Overview from './mg/Overview';
import Documents from './mg/Documents';
import Trends from './mg/Trends';
import Ask from './mg/Ask';

type Tab = 'overview' | 'documents' | 'trends' | 'ask';
const TABS: [Tab, string][] = [['overview', 'Overview'], ['trends', 'Trends & Outlook'], ['ask', 'Ask MarginGuard'], ['documents', 'Inbox']];

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [docId, setDocId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Alert[]>([]);
  const restaurant = usePoll(() => api.restaurant(), 0);
  const health = usePoll(() => api.health(), 10000);
  const alerts = usePoll(() => api.alerts('new'), 5000);
  const seen = useRef<Set<string> | null>(null);
  // Refresh the bell immediately when an alert is acknowledged or resolved elsewhere on the page.
  useEffect(() => {
    const onChange = () => alerts.refresh();
    window.addEventListener('mg:alerts-changed', onChange);
    return () => window.removeEventListener('mg:alerts-changed', onChange);
  }, [alerts]);

  // Pop a toast for every alert that appears after the page loaded.
  useEffect(() => {
    if (!alerts.data) return;
    const ids = alerts.data.items.map((a) => a.id);
    if (seen.current === null) { seen.current = new Set(ids); return; }
    const fresh = alerts.data.items.filter((a) => !seen.current!.has(a.id));
    fresh.forEach((a) => seen.current!.add(a.id));
    if (fresh.length) {
      setToasts((t) => [...t, ...fresh]);
      fresh.forEach((a) => window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== a.id)), 9000));
    }
  }, [alerts.data]);

  const newCount = alerts.data?.total ?? 0;
  const online = health.data !== null && !health.error;

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">M</span>
          <div><b>MarginGuard</b><small>{restaurant.data?.name ?? 'Restaurant finance watchdog'}</small></div>
        </div>
        <nav className="tabs">
          {TABS.map(([id, name]) => <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{name}</button>)}
        </nav>
        <div className="top-right">
          {restaurant.data?.is_demo !== false && <span className="demo">Fictional demo data</span>}
          <span className={`conn ${online ? 'ok' : 'down'}`} title={online ? 'Backend connected' : 'Backend not reachable'}><i />{online ? 'Live' : 'Offline'}</span>
          <button className="bell" onClick={() => setTab('overview')} title="Alerts">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1Z" fill="currentColor" /></svg>
            {newCount > 0 && <span className="bell-count">{newCount}</span>}
          </button>
        </div>
      </header>

      <main className="content">
        {tab === 'overview' && <Overview go={setTab} />}
        {tab === 'documents' && <Documents selectedId={docId} onSelect={setDocId} />}
        {tab === 'trends' && <Trends />}
        {tab === 'ask' && <Ask />}
      </main>

      <div className="toasts">
        {toasts.map((a) => (
          <button key={a.id} className={`toast ${a.severity}`} onClick={() => { setTab('overview'); setToasts((t) => t.filter((x) => x.id !== a.id)); }}>
            <b>New alert · {a.title}</b><span>{a.message}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
