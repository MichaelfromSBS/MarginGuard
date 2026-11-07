import { useState } from 'react';
import { api, errorText, isNotYet, usePoll } from './client';
import { MetricCard } from './Overview';
import { money, pctChange, shortDate } from './format';
import { Card, Empty, ErrorBox, NotYet, PriceChart } from './ui';

export default function Trends() {
  const catalog = usePoll(() => api.catalog(), 0);
  const [ingredient, setIngredient] = useState('beef');
  const prices = usePoll(() => api.prices(ingredient), 5000, [ingredient]);
  const forecast = usePoll(() => api.forecasts(), 15000);
  const invoices = usePoll(() => api.invoices(), 10000);
  const lineToInvoice = new Map<string, string>();
  (invoices.data?.items ?? []).forEach((inv) => inv.items.forEach((line) => lineToInvoice.set(line.id, `${inv.invoice_number} · ${inv.vendor_name}`)));
  const ing = catalog.data?.ingredients.find((i) => i.id === ingredient);
  const items = prices.data?.items ?? [];
  const unit = ing?.base_unit ?? 'unit';
  const latest = forecast.data?.items[0];

  return (
    <div className="stack">
      <Card title="Ingredient price history" action={<small className="muted">step = price holds until the next invoice</small>}>
        <div className="chips">
          {(catalog.data?.ingredients ?? []).map((i) => (
            <button key={i.id} className={`chip ${i.id === ingredient ? 'on' : ''}`} onClick={() => setIngredient(i.id)}>{i.name}</button>
          ))}
        </div>
        {prices.error ? <ErrorBox>{errorText(prices.error)}</ErrorBox> : null}
        <PriceChart unit={unit} points={items.map((p) => ({ date: p.effective_date, value: Number(p.unit_cost), ref: p.id }))} />
        {items.length > 0 && (
          <table className="tbl">
            <thead><tr><th>Effective</th><th className="r">Cost per {unit}</th><th className="r">Change</th><th>Source</th></tr></thead>
            <tbody>{[...items].reverse().map((p, i, arr) => {
              const prev = arr[i + 1];
              const ch = prev ? pctChange(prev.unit_cost, p.unit_cost) : null;
              return (
                <tr key={p.id} className={ch !== null && ch > 0.05 ? 'up' : ''}>
                  <td>{shortDate(p.effective_date)}</td>
                  <td className="r strong">{money(p.unit_cost)}</td>
                  <td className="r">{ch === null || Math.abs(ch) < 0.05 ? <span className="muted">—</span> : <span className={ch > 0 ? 'upval' : 'downval'}>{ch > 0 ? '▲' : '▼'} {Math.abs(ch).toFixed(1)}%</span>}</td>
                  <td className="muted">{lineToInvoice.get(p.invoice_line_id) ?? 'Supplier invoice'}</td>
                </tr>
              );
            })}</tbody>
          </table>
        )}
      </Card>

      <Card title="Sales and December outlook">
        {forecast.error ? (isNotYet(forecast.error) ? <NotYet checkpoint={3} what="Daily sales trends and the next-month forecast (base, low and high scenarios)" /> : <ErrorBox>{errorText(forecast.error)}</ErrorBox>) : null}
        {forecast.data && !latest && <Empty>No forecast has been calculated yet.</Empty>}
        {latest && (
          <>
            <p className="muted">{latest.method} · {shortDate(latest.horizon.start)} – {shortDate(latest.horizon.end)} · {latest.status}</p>
            <div className="metrics">{latest.metrics.map((m) => <MetricCard key={m.id} m={m} />)}</div>
            {latest.assumptions.length > 0 && <div className="assume"><b>Assumptions</b><ul>{latest.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></div>}
          </>
        )}
      </Card>
    </div>
  );
}
