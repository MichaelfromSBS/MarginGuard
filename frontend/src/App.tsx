import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Alert } from './marginguard-api';
import { api, usePoll } from './mg/client';
import Overview from './mg/Overview';
import Documents from './mg/Documents';
import Trends from './mg/Trends';
import FloatingChat from './mg/FloatingChat';
import useAlerts from './mg/useAlerts';
import { alertPreview } from './mg/Alerts';

type Tab = 'overview' | 'documents' | 'trends';
const TABS: [Tab, string][] = [['overview', 'Overview'], ['trends', 'Trends & Outlook'], ['documents', 'Inbox']];

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [direction, setDirection] = useState('forward');
  const [docId, setDocId] = useState<string | null>(null);
  const [alertSelection, setAlertSelection] = useState<{ id: string | null; token: number } | null>(null);
  const [toasts, setToasts] = useState<Alert[]>([]);
  const restaurant = usePoll(() => api.restaurant(), 0);
  const health = usePoll(() => api.health(), 10000);
  const alerts = useAlerts();
  const seen = useRef<Set<string> | null>(null);
  // Pop a toast for every alert that appears after the page loaded.
  useEffect(() => {
    if (!alerts.data) return;
    const ids = alerts.data.items.map((a) => a.id);
    if (seen.current === null) { seen.current = new Set(ids); return; }
    const fresh = alerts.data.items.filter((a) => a.status === 'new' && !seen.current!.has(a.id));
    ids.forEach((id) => seen.current!.add(id));
    const active = new Set(alerts.data.items.filter((a) => a.status === 'new').map((a) => a.id));
    setToasts((t) => [...t.filter((a) => active.has(a.id)), ...fresh]);
    if (fresh.length) {
      fresh.forEach((a) => window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== a.id)), 9000));
    }
  }, [alerts.data]);

  const newCount = alerts.data?.newCount ?? 0;
  const online = health.data !== null && !health.error;
  // Reset before paint, rather than briefly showing the new view at the old scroll offset.
  useLayoutEffect(() => { window.scrollTo(0, 0); }, [tab]);
  const navigate = (next: Tab) => {
    if (next === tab) return;
    setDirection(TABS.findIndex(([id]) => id === next) > TABS.findIndex(([id]) => id === tab) ? 'forward' : 'backward');
    setTab(next);
  };
  const openAlert = (id: string) => {
    setAlertSelection((previous) => ({ id, token: (previous?.token ?? 0) + 1 }));
    navigate('documents');
    setToasts((items) => items.filter((a) => a.id !== id));
  };
  const openNotifications = () => {
    setAlertSelection((previous) => ({ id: null, token: (previous?.token ?? 0) + 1 }));
    navigate('documents');
  };
  const openSource = (id: string) => { setDocId(id); navigate('documents'); };

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">M</span>
          <div><b>MarginGuard</b><small>{restaurant.data?.name ?? 'Restaurant finance watchdog'}</small></div>
        </div>
        <nav className="tabs" aria-label="Main navigation">
          {TABS.map(([id, name]) => <button key={id} className={tab === id ? 'on' : ''} aria-current={tab === id ? 'page' : undefined} onClick={() => navigate(id)}>{name}</button>)}
        </nav>
        <div className="top-right">
          {restaurant.data?.is_demo !== false && <span className="demo">{health.data?.demo_as_of ? `Demo · ${health.data.demo_as_of}${health.data.mode === 'mock' ? ' · AI off' : ''}` : 'Fictional demo data'}</span>}
          <span className={`conn ${online ? 'ok' : 'down'}`} title={online ? 'Backend connected' : 'Backend not reachable'}><i />{online ? 'Live' : 'Offline'}</span>
          <button className="bell" onClick={openNotifications} aria-label="Notifications" title={newCount ? `${newCount} new notification${newCount === 1 ? '' : 's'}` : 'Notifications'}>
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1Z" fill="currentColor" /></svg>
            {newCount > 0 && <span className="bell-count">{newCount}</span>}
          </button>
        </div>
      </header>

      <main className="content" data-direction={direction}>
        <div key="overview" className={`tab-panel ${tab === 'overview' ? 'is-active' : ''}`} hidden={tab !== 'overview'}><Overview go={navigate} alerts={alerts} onOpenAlert={openAlert} onSource={openSource} demoAsOf={health.data?.demo_as_of} /></div>
        <div key="trends" className={`tab-panel ${tab === 'trends' ? 'is-active' : ''}`} hidden={tab !== 'trends'}><Trends demoAsOf={health.data?.demo_as_of} /></div>
        {/* Preload Inbox and retain its list/upload state while another tab is active. */}
        <div key="documents" className={`tab-panel ${tab === 'documents' ? 'is-active' : ''}`} hidden={tab !== 'documents'}><Documents selectedId={docId} onSelect={setDocId} alerts={alerts} alertSelection={alertSelection} /></div>
      </main>

      <FloatingChat visible={tab === 'overview'} onSource={openSource} />

      <div className="toasts">
        {toasts.map((a) => (
          <div key={a.id} className={`toast ${a.severity}`} role="status">
            <span className="toast-label">New alert</span>
            <button className="toast-open" onClick={() => openAlert(a.id)}><b>{a.title}</b><span>{alertPreview(a)}</span><small>View details →</small></button>
            <button className="toast-close" aria-label="Dismiss notification" onClick={() => setToasts((items) => items.filter((x) => x.id !== a.id))}>×</button>
          </div>
        ))}
      </div>
    </div>
  );
}
