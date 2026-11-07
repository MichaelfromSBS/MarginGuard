import { useState } from 'react';
import type { Alert, Metric } from '../marginguard-api';
import { api, errorText, isNotYet, loadDocuments, usePoll } from './client';
import { localDate, money, pctChange, shortDate, timeAgo } from './format';
import { Card, ErrorBox, NotYet } from './ui';
import { MetricCard } from './Metrics';
import Ask from './Ask';

type Go = (tab: 'trends' | 'documents') => void;

export function AlertItem({ a, onChanged }: { a: Alert; onChanged?: () => void }) {
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const act = async (fn: (id: string) => Promise<Alert>) => {
    setBusy(true); setErr('');
    try { await fn(a.id); onChanged?.(); window.dispatchEvent(new Event('mg:alerts-changed')); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <div className={`alert ${a.severity} ${a.status === 'acknowledged' ? 'seen' : ''}`}>
      <div className="alert-main">
        <b>{a.title}</b>
        <p>{a.message}</p>
        {a.suggestion && <span className="suggest"><b>Suggested next step:</b> {a.suggestion}{a.explanation_status === 'ai' ? ' (AI suggestion)' : ''}</span>}
        <small>{timeAgo(a.created_at)}{a.evidence.length ? ` · ${a.evidence.length} source${a.evidence.length > 1 ? 's' : ''}` : ''}</small>
        {err && <small className="err">{err}</small>}
      </div>
      <div className="alert-actions">
        {a.status === 'new' && <button className="ghost" disabled={busy} onClick={() => act(api.acknowledge)}>Acknowledge</button>}
        <button className="ghost" disabled={busy} onClick={() => act(api.resolve)} title="Mark as handled and remove from the list">Resolve</button>
      </div>
    </div>
  );
}

/** A lightweight attention row that links to the page where it can be handled. */
function Task({ tone, title, text, action, onClick }: { tone: 'warn' | 'info'; title: string; text: string; action: string; onClick: () => void }) {
  return (
    <div className={`alert task ${tone}`}>
      <div className="alert-main"><b>{title}</b><p>{text}</p></div>
      <button className="ghost" onClick={onClick}>{action} →</button>
    </div>
  );
}

const SALES = ['sales.net_revenue', 'sales.orders', 'sales.average_order_revenue', 'sales.units'];
const OUTLOOK = ['forecast.revenue', 'forecast.ingredient_cost'];
const GHOST: Record<string, string> = {
  'sales.net_revenue': 'Net sales', 'sales.orders': 'Orders', 'sales.average_order_revenue': 'Average order value', 'sales.units': 'Dishes sold',
  'forecast.revenue': 'Projected net sales', 'forecast.ingredient_cost': 'Projected ingredient cost',
};
const RECENT_DAYS = 14;

export default function Overview({ go, onSource }: { go: Go; onSource: (id: string) => void }) {
  // Archived resolved findings cannot displace either live list's first page.
  const alerts = usePoll(async () => {
    const [fresh, acknowledged] = await Promise.all([api.alerts('new'), api.alerts('acknowledged')]);
    return { items: [...fresh.items, ...acknowledged.items] };
  }, 5000);
  const capabilities = usePoll(() => api.capabilities(), 0);
  const worker = usePoll(() => api.worker(), 5000);
  const dash = usePoll(() => api.dashboard(), 15000);
  const docs = usePoll(() => loadDocuments(false), 10000);
  const catalog = usePoll(() => api.catalog(), 0);
  const prices = usePoll(async () => {
    if (!catalog.data) return [];
    return Promise.all(catalog.data.ingredients.map(async (ing) => ({ ing, items: (await api.prices(ing.id)).items })));
  }, 10000, [catalog.data]);

  const open = (alerts.data?.items ?? []).filter((a) => a.status === 'new');
  const seen = (alerts.data?.items ?? []).filter((a) => a.status === 'acknowledged');
  const monitoringAvailable = capabilities.data?.capabilities.some((c) => c.name === 'background_processing_and_alerts' && c.available);
  const monitoring = monitoringAvailable && worker.data?.status === 'running' && !worker.error && !worker.data.error_code;
  const review = (docs.data ?? []).filter((d) => d.status === 'needs_review' || d.status === 'failed');
  const forecast = dash.data?.forecast ?? null;
  const forecastStale = forecast?.status === 'pending';
  const attentionCount = open.length + (review.length ? 1 : 0) + (forecastStale ? 1 : 0);

  const pick = (ids: string[], from: Metric[] | undefined) => ids.map((id) => ({ id, m: from?.find((x) => x.id === id) }));
  const sales = pick(SALES, dash.data?.metrics);
  const outlook = pick(OUTLOOK, forecast?.status === 'ready' && !dash.error ? forecast.metrics : undefined);

  // Only supplier price changes from the last two weeks; full history lives in Trends & Outlook.
  const cutoff = new Date(Date.now() - RECENT_DAYS * 86400000).toISOString().slice(0, 10);
  const changes = (prices.data ?? []).flatMap(({ ing, items }) => {
    const eff = items.filter((p) => p.effective_date <= localDate());
    const selected = dash.data?.dish_costs.flatMap((d) => d.ingredients).find((i) => i.ingredient_id === ing.id)?.evidence?.record_id;
    const cur = eff.find((p) => p.invoice_line_id === selected) ?? eff.at(-1);
    // Compare with the latest price from an earlier date (several invoices can share a date).
    const prev = cur ? eff.filter((p) => p.effective_date < cur.effective_date).at(-1) : undefined;
    if (!cur || !prev || cur.effective_date < cutoff) return [];
    const ch = pctChange(prev.unit_cost, cur.unit_cost);
    return ch !== null && Math.abs(ch) >= 0.05 ? [{ ing, cur, prev, ch }] : [];
  }).sort((a, b) => Math.abs(b.ch) - Math.abs(a.ch));

  return (
    <div className="stack">
      <Card title={<>Needs attention {attentionCount > 0 && <span className="count">{attentionCount}</span>}</>}>
        {alerts.error ? <ErrorBox>{errorText(alerts.error)}</ErrorBox> : null}
        {open.map((a) => <AlertItem key={a.id} a={a} onChanged={alerts.refresh} />)}
        {review.length > 0 && <Task tone="warn" title={`${review.length} document${review.length > 1 ? 's' : ''} need${review.length > 1 ? '' : 's'} review`}
          text="Held out of the books until checked." action="Open Inbox" onClick={() => go('documents')} />}
        {forecastStale && <Task tone="info" title="Next-month forecast is out of date" text="New records arrived since it was calculated." action="Recalculate" onClick={() => go('trends')} />}
        {attentionCount === 0 && (alerts.loading || worker.loading ? <p className="muted">Checking for alerts…</p>
          : alerts.error ? null
          : monitoring ? <p className="allclear">All clear.</p>
          : monitoringAvailable ? <p className="issues">Automatic monitoring is unavailable. Alerts and forecasts may be out of date.</p>
          : <NotYet checkpoint={4} what="Cost increases and yesterday’s unusual sales" />)}
        {seen.length > 0 && (
          <details className="seen-list">
            <summary>Acknowledged ({seen.length}): resolve when handled</summary>
            {seen.map((a) => <AlertItem key={a.id} a={a} onChanged={alerts.refresh} />)}
          </details>
        )}
      </Card>

      <section>
        <div className="section-head"><h3>Sales</h3>{sales[0].m?.period && <small className="muted">last 7 days</small>}</div>
        <div className="metrics">
          {sales.map(({ id, m }) => m ? <MetricCard key={id} m={m} /> : <Ghost key={id} label={GHOST[id]} />)}
        </div>
        {dash.error ? (isNotYet(dash.error) ? <NotYet checkpoint={3} what="Sales figures" /> : <ErrorBox>{errorText(dash.error)}</ErrorBox>) : null}
      </section>

      <div className="grid2 even">
        <section>
          <div className="section-head"><h3>Next month</h3><button className="link" onClick={() => go('trends')}>Full outlook →</button></div>
          <div className="metrics two">
            {outlook.map(({ id, m }) => m ? <MetricCard key={id} m={m} /> : <Ghost key={id} label={GHOST[id]} note={forecast ? 'Recalculate in Trends & Outlook' : 'Calculate in Trends & Outlook'} />)}
          </div>
        </section>
        <section>
          <div className="section-head"><h3>Supplier price changes</h3><button className="link" onClick={() => go('trends')}>Price history →</button></div>
          <Card className="changes">
            {catalog.error || prices.error ? <ErrorBox>{errorText(catalog.error || prices.error)}</ErrorBox>
              : catalog.loading || prices.loading ? <p className="muted">Loading supplier prices…</p>
              : changes.length === 0 ? <p className="allclear">No price changes in the last {RECENT_DAYS} days.</p> : changes.map(({ ing, cur, prev, ch }) => (
              <div key={ing.id} className="change">
                <span><b>{ing.name}</b><small>{shortDate(cur.effective_date)}</small></span>
                <span className="r">{money(prev.unit_cost)} → <b>{money(cur.unit_cost)}</b>/{ing.base_unit}</span>
                <span className={ch > 0 ? 'upval' : 'downval'}>{ch > 0 ? '▲' : '▼'} {Math.abs(ch).toFixed(1)}%</span>
              </div>
            ))}
          </Card>
        </section>
      </div>

      <Ask onSource={onSource} />
    </div>
  );
}

function Ghost({ label, note }: { label: string; note?: string }) {
  return <div className="metric ghost"><div className="metric-top"><span>{label}</span></div><div className="metric-value">—</div>{note && <div className="metric-foot">{note}</div>}</div>;
}
