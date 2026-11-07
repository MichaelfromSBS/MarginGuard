import { useState } from 'react';
import { api, errorText, isNotYet, usePoll } from './client';
import Forecast from './Forecast';
import { decimal, localDate, money, pctChange, qty, shortDate } from './format';
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
  const names = Object.fromEntries((catalog.data?.ingredients ?? []).map((i) => [i.id, i.name]));

  return (
    <div className="stack">
      {dashboard.error ? (isNotYet(dashboard.error) ? <NotYet checkpoint={3} what="Sales and next-month forecasts" /> : <ErrorBox>{errorText(dashboard.error)}</ErrorBox>) : null}
      {dashboard.data && !dashboard.error && <Forecast snapshot={dashboard.data.forecast} onChanged={dashboard.refresh} />}

      {catalog.data && (
        <Card title="Dish costs" action={<small className="muted">restock cost per dish = ingredients for one dish at today’s supplier prices</small>}>
          <div className="table-scroll"><table className="tbl">
            <thead><tr><th>Dish</th><th>Recipe</th><th className="r">Menu price</th><th className="r">Restock cost per dish</th><th className="r">Ingredient share</th></tr></thead>
            <tbody>{catalog.data.dishes.map((dish) => {
              const cost = dashboard.data?.dish_costs.find((d) => d.dish_id === dish.id);
              const price = dish.prices.filter((p) => p.channel_id === 'in_store' && p.effective_date <= localDate()).at(-1);
              const recipe = dish.recipes.filter((r) => r.effective_date <= localDate()).at(-1);
              const share = cost?.ingredient_cost && price && Number(price.price) > 0 ? (Number(cost.ingredient_cost) / Number(price.price)) * 100 : null;
              return (
                <tr key={dish.id}>
                  <td className="strong">{dish.name}</td>
                  <td className="muted small">{recipe?.items.map((it) => `${qty(it.quantity)} ${it.unit === 'each' ? '×' : it.unit} ${(names[it.ingredient_id] ?? it.ingredient_id).toLowerCase()}`).join(' · ')}</td>
                  <td className="r">{money(price?.price)}</td>
                  <td className="r strong">{cost ? money(cost.ingredient_cost) : '—'}</td>
                  <td className="r muted">{share === null ? '—' : `${share.toFixed(1)}%`}</td>
                </tr>
              );
            })}</tbody>
          </table></div>
        </Card>
      )}

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

      {dashboard.data && !dashboard.error && (
        <Card title="Daily sales" action={<small className="muted">{dashboard.data.sales && `${shortDate(dashboard.data.sales.period.start)} – ${shortDate(dashboard.data.sales.period.end)}`}</small>}>
          {dashboard.data.sales?.coverage.status !== 'complete' && <p className="issues">Receipt coverage is incomplete. These are observed totals only.</p>}
          {dashboard.data.sales?.by_day.length ? <div className="table-scroll"><table className="tbl"><thead><tr><th>Date</th><th className="r">Orders</th><th className="r">Dishes sold</th><th className="r">Net sales</th></tr></thead><tbody>{dashboard.data.sales.by_day.map((d) => <tr key={d.date}><td>{shortDate(d.date!)}</td><td className="r">{d.orders}</td><td className="r">{decimal(d.units, 0)}</td><td className="r">{money(d.net_revenue)}</td></tr>)}</tbody></table></div> : <Empty>No observed sales in this period.</Empty>}
        </Card>
      )}
    </div>
  );
}
