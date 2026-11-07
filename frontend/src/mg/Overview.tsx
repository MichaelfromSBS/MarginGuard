import { useState } from 'react';
import type { Alert, Metric } from '../marginguard-api';
import { api, errorText, isNotYet, usePoll } from './client';
import { decimal, label, money, pctChange, qty, shortDate, timeAgo } from './format';
import { Card, Empty, ErrorBox, NotYet, Pill } from './ui';

export function formatMetric(m: Metric) {
  if (m.value === null) return '—';
  switch (m.unit) {
    case 'USD': return money(m.value);
    case 'percent': return `${decimal(m.value, 1)}%`;
    case 'lb': return `${decimal(m.value, 1)} lb`;
    default: return decimal(m.value, 0);
  }
}
const KIND: Record<Metric['kind'], [string, 'ok' | 'info' | 'accent']> = { actual: ['Observed', 'ok'], modeled: ['Modeled', 'info'], projected: ['Projected', 'accent'] };

export function MetricCard({ m }: { m: Metric }) {
  return (
    <div className="metric">
      <div className="metric-top"><span>{m.label}</span><Pill tone={KIND[m.kind][1]}>{KIND[m.kind][0]}</Pill></div>
      <div className="metric-value">{formatMetric(m)}</div>
      <div className="metric-foot">
        {m.period ? `${shortDate(m.period.start)} – ${shortDate(m.period.end)}` : ''}
        {m.coverage !== 'complete' && <Pill tone="warn">{label(m.coverage)} data</Pill>}
      </div>
    </div>
  );
}

export function AlertItem({ a, onChanged }: { a: Alert; onChanged?: () => void }) {
  const [err, setErr] = useState('');
  const ack = async () => {
    try { await api.acknowledge(a.id); onChanged?.(); } catch (e) { setErr(isNotYet(e) ? 'Acknowledging alerts arrives with checkpoint 4.' : errorText(e)); }
  };
  return (
    <div className={`alert ${a.severity}`}>
      <div className="alert-main">
        <b>{a.title}</b>
        <p>{a.message}</p>
        <small>{timeAgo(a.created_at)}{a.evidence.length ? ` · ${a.evidence.length} source${a.evidence.length > 1 ? 's' : ''}` : ''}{a.status !== 'new' ? ` · ${a.status}` : ''}</small>
        {err && <small className="err">{err}</small>}
      </div>
      {a.status === 'new' && <button className="ghost" onClick={ack}>Acknowledge</button>}
    </div>
  );
}

const PLACEHOLDER = ['Net sales (last 7 days)', 'Orders (last 7 days)', 'Average order value (last 7 days)', 'December projected revenue'];

export default function Overview() {
  const alerts = usePoll(() => api.alerts(), 5000);
  const dash = usePoll(() => api.dashboard(), 15000);
  const catalog = usePoll(() => api.catalog(), 0);
  const prices = usePoll(async () => {
    if (!catalog.data) return [];
    return Promise.all(catalog.data.ingredients.map(async (ing) => ({ ing, items: (await api.prices(ing.id)).items })));
  }, 5000, [catalog.data]);
  const open = (alerts.data?.items ?? []).filter((a) => a.status !== 'resolved').reverse();

  return (
    <div className="stack">
      <Card title={<>Needs attention {open.length > 0 && <span className="count">{open.length}</span>}</>}>
        {alerts.error ? <ErrorBox>{errorText(alerts.error)}</ErrorBox> : null}
        {alerts.data && open.length === 0 && <Empty>All clear. MarginGuard will flag price spikes, cost increases, unusual sales days and data problems here, automatically.</Empty>}
        {open.map((a) => <AlertItem key={a.id} a={a} onChanged={alerts.refresh} />)}
      </Card>

      <div className="metrics">
        {dash.data ? dash.data.metrics.slice(0, 8).map((m) => <MetricCard key={m.id} m={m} />)
          : PLACEHOLDER.map((p) => <div key={p} className="metric ghost"><div className="metric-top"><span>{p}</span></div><div className="metric-value">—</div></div>)}
      </div>
      {dash.error ? (isNotYet(dash.error) ? <NotYet checkpoint={3} what="Sales, dish costs and next-month projections" /> : <ErrorBox>{errorText(dash.error)}</ErrorBox>) : null}

      <Card title="Ingredient costs" action={<small className="muted">from supplier invoices</small>}>
          {prices.data && prices.data.length > 0 ? (
            <table className="tbl">
              <thead><tr><th>Ingredient</th><th className="r">Current</th><th className="r">Previous</th><th className="r">Change</th><th className="r">Since</th></tr></thead>
              <tbody>{prices.data.map(({ ing, items }) => {
                const cur = items[items.length - 1], prev = items[items.length - 2];
                const ch = cur && prev ? pctChange(prev.unit_cost, cur.unit_cost) : null;
                return (
                  <tr key={ing.id} className={ch !== null && ch > 0.05 ? 'up' : ''}>
                    <td>{ing.name}</td>
                    <td className="r strong">{cur ? `${money(cur.unit_cost)}/${ing.base_unit}` : '—'}</td>
                    <td className="r muted">{prev ? money(prev.unit_cost) : '—'}</td>
                    <td className="r">{ch === null ? '—' : Math.abs(ch) < 0.05 ? <span className="muted">no change</span> : <span className={ch > 0 ? 'upval' : 'downval'}>{ch > 0 ? '▲' : '▼'} {Math.abs(ch).toFixed(1)}%</span>}</td>
                    <td className="r muted">{cur ? shortDate(cur.effective_date) : '—'}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          ) : <Empty>{prices.error ? errorText(prices.error) : 'Loading…'}</Empty>}
        </Card>


      {catalog.data && (
        <Card title="Menu" action={<small className="muted">recipes used for dish costs</small>}>
          <div className="menu">
            {catalog.data.dishes.map((dish) => {
              const price = dish.prices.find((p) => p.channel_id === 'in_store') ?? dish.prices[0];
              const recipe = dish.recipes[dish.recipes.length - 1];
              const names = Object.fromEntries(catalog.data!.ingredients.map((i) => [i.id, i.name]));
              return (
                <div key={dish.id} className="dish">
                  <div className="dish-head"><b>{dish.name}</b><span>{money(price?.price)}</span></div>
                  <small>{recipe?.items.map((it) => `${qty(it.quantity)} ${it.unit === 'each' ? '×' : it.unit} ${(names[it.ingredient_id] ?? it.ingredient_id).toLowerCase()}`).join(' · ')}</small>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}
