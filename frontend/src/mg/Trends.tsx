import { useState } from 'react';
import { api, errorText, isNotYet, usePoll } from './client';
import Forecast from './Forecast';
import { decimal, money, pctChange, shortDate } from './format';
import { Card, Empty, ErrorBox, NotYet, PriceChart } from './ui';

export default function Trends() {
  const catalog = usePoll(() => api.catalog(), 0);
  const [ingredient, setIngredient] = useState('beef');
  const prices = usePoll(() => api.prices(ingredient), 5000, [ingredient]);
  const dashboard = usePoll(() => api.dashboard(), 15000);
  const invoices = usePoll(() => api.invoices(), 10000);
  const lineToInvoice = new Map<string, string>();
  (invoices.data?.items ?? []).forEach((inv) => inv.items.forEach((line) => lineToInvoice.set(line.id, `${inv.invoice_number} · ${inv.vendor_name}`)));
  const ing = catalog.data?.ingredients.find((i) => i.id === ingredient);
  const items = prices.data?.items ?? [];
  const unit = ing?.base_unit ?? 'unit';

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

      {dashboard.error ? (isNotYet(dashboard.error) ? <NotYet checkpoint={3} what="Sales and next-month forecasts" /> : <ErrorBox>{errorText(dashboard.error)}</ErrorBox>) : null}
      {dashboard.data && !dashboard.error && <>
        <Card title="Observed daily sales" action={<small className="muted">{dashboard.data.sales && `${shortDate(dashboard.data.sales.period.start)} – ${shortDate(dashboard.data.sales.period.end)}`}</small>}>
          {dashboard.data.sales?.coverage.status !== 'complete' && <p className="issues">Receipt coverage is incomplete. These are observed totals only.</p>}
          {dashboard.data.sales?.by_day.length ? <div className="table-scroll"><table className="tbl"><thead><tr><th>Date</th><th className="r">Orders</th><th className="r">Units</th><th className="r">Net item revenue</th></tr></thead><tbody>{dashboard.data.sales.by_day.map((d) => <tr key={d.date}><td>{shortDate(d.date!)}</td><td className="r">{d.orders}</td><td className="r">{decimal(d.units, 0)}</td><td className="r">{money(d.net_revenue)}</td></tr>)}</tbody></table></div> : <Empty>No observed sales in this period.</Empty>}
        </Card>
        <Forecast snapshot={dashboard.data.forecast} onChanged={dashboard.refresh} />
      </>}
    </div>
  );
}
