import { useState } from 'react';
import type { Alert } from '../marginguard-api';
import { api, errorText, isNotYet, usePoll } from './client';
import { localDate, money, pctChange, qty, shortDate, timeAgo } from './format';
import { Card, Empty, ErrorBox, NotYet, Pill } from './ui';
import { MetricCard } from './Metrics';
import Forecast from './Forecast';

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

const PLACEHOLDER = ['Units sold', 'Orders', 'Net item revenue', 'Average order revenue'];

export default function Overview() {
  const alerts = usePoll(() => api.alerts(), 5000);
  const capabilities = usePoll(() => api.capabilities(), 0);
  const dash = usePoll(() => api.dashboard(), 15000);
  const catalog = usePoll(() => api.catalog(), 0);
  const prices = usePoll(async () => {
    if (!catalog.data) return [];
    return Promise.all(catalog.data.ingredients.map(async (ing) => ({ ing, items: (await api.prices(ing.id)).items })));
  }, 5000, [catalog.data]);
  const open = (alerts.data?.items ?? []).filter((a) => a.status !== 'resolved').reverse();
  const monitoring = capabilities.data?.capabilities.some((c) => c.name === 'background_processing_and_alerts' && c.available);

  return (
    <div className="stack">
      <Card title={<>Needs attention {open.length > 0 && <span className="count">{open.length}</span>}</>}>
        {alerts.error ? <ErrorBox>{errorText(alerts.error)}</ErrorBox> : null}
        {alerts.data && open.length === 0 && (monitoring ? <Empty>No alerts recorded.</Empty> : <NotYet checkpoint={4} what="Automatic monitoring and alerts" />)}
        {open.map((a) => <AlertItem key={a.id} a={a} onChanged={alerts.refresh} />)}
      </Card>

      <div className="metrics">
        {dash.data ? dash.data.metrics.slice(0, 8).map((m) => <MetricCard key={m.id} m={m} />)
          : PLACEHOLDER.map((p) => <div key={p} className="metric ghost"><div className="metric-top"><span>{p}</span></div><div className="metric-value">—</div></div>)}
      </div>
      {dash.error ? (isNotYet(dash.error) ? <NotYet checkpoint={3} what="Sales, dish costs and next-month projections" /> : <ErrorBox>{errorText(dash.error)}</ErrorBox>) : null}
      {dash.data && !dash.error && <Forecast snapshot={dash.data.forecast} onChanged={dash.refresh} />}

      <Card title="Ingredient costs" action={<small className="muted">from supplier invoices</small>}>
          {prices.data && prices.data.length > 0 ? (
            <div className="table-scroll"><table className="tbl">
              <thead><tr><th>Ingredient</th><th className="r">Current</th><th className="r">Previous</th><th className="r">Change</th><th className="r">Since</th></tr></thead>
              <tbody>{prices.data.map(({ ing, items }) => {
                const effective = items.filter((p) => p.effective_date <= localDate());
                const selected = dash.data?.dish_costs.flatMap((d) => d.ingredients).find((i) => i.ingredient_id === ing.id)?.evidence?.record_id;
                const cur = effective.find((p) => p.invoice_line_id === selected) ?? effective[effective.length - 1];
                const prev = effective.filter((p) => p.id !== cur?.id && p.effective_date <= (cur?.effective_date ?? '')).at(-1);
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
            </table></div>
          ) : <Empty>{prices.error ? errorText(prices.error) : 'Loading…'}</Empty>}
        </Card>


      {catalog.data && (
        <Card title="Menu" action={<small className="muted">recipes used for dish costs</small>}>
          <div className="menu">
            {catalog.data.dishes.map((dish) => {
              const cost = dash.data?.dish_costs.find((d) => d.dish_id === dish.id);
              const price = dish.prices.filter((p) => p.channel_id === 'in_store' && p.effective_date <= localDate()).at(-1);
              const recipe = dish.recipes.filter((r) => r.effective_date <= localDate()).at(-1);
              const names = Object.fromEntries(catalog.data!.ingredients.map((i) => [i.id, i.name]));
              return (
                <div key={dish.id} className="dish">
                  <div className="dish-head"><b>{dish.name}</b><span>{money(price?.price)}</span></div>
                  <small>{recipe?.items.map((it) => `${qty(it.quantity)} ${it.unit === 'each' ? '×' : it.unit} ${(names[it.ingredient_id] ?? it.ingredient_id).toLowerCase()}`).join(' · ')}</small>
                  {cost && <p className="hint">Replacement ingredient cost: <b>{money(cost.ingredient_cost)}</b>{cost.limitations.length ? ` · ${cost.limitations.join(' ')}` : ''}</p>}
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}
