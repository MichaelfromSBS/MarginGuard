import { useState } from 'react';
import type { ForecastResponse } from '../marginguard-api';
import { api, errorText } from './client';
import { decimal, label, money, shortDate } from './format';
import { MetricCard } from './Metrics';
import { Card, Empty, ErrorBox, Pill } from './ui';

export default function Forecast({ snapshot, onChanged }: { snapshot: ForecastResponse | null; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const calculate = async () => {
    setBusy(true); setError('');
    try { await api.recalculate(); onChanged(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const ready = snapshot?.status === 'ready';
  return (
    <Card title="Next-month outlook" action={<button className="primary" disabled={busy} onClick={calculate}>{busy ? 'Calculating…' : snapshot ? 'Recalculate forecast' : 'Calculate forecast'}</button>}>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!snapshot && <Empty>Calculate a forecast from complete past sales days and current ingredient prices.</Empty>}
      {snapshot && <>
        <p className="muted">{shortDate(snapshot.horizon.start)} – {shortDate(snapshot.horizon.end)} · <Pill tone={ready ? 'ok' : 'warn'}>{snapshot.status === 'pending' ? 'Out of date' : label(snapshot.status)}</Pill></p>
        {snapshot.status === 'pending' && <div className="issues">Records changed since this calculation. Recalculate to see a current forecast.</div>}
        {snapshot.status === 'insufficient_history' && <Empty>A complete restaurant forecast needs more history or missing planning inputs. See the details below.</Empty>}
        {ready && <>
          <div className="metrics">{snapshot.metrics.map((m) => <MetricCard key={m.id} m={m} />)}</div>
          <div className="subsection">
            <h4>Ingredients needed next month</h4>
            <p className="hint">Projected dishes sold × recipe amounts, priced at today’s supplier prices. This is expected usage, not an order quantity: stock already on hand isn’t counted.</p>
            <div className="table-scroll"><table className="tbl">
              <thead><tr><th>Ingredient</th><th className="r">Amount needed</th><th className="r">Price today</th><th className="r">Cost</th></tr></thead>
              <tbody>{snapshot.ingredients.map((i) => <tr key={i.ingredient_id} title={i.evidence.quote ? `Price from invoice: "${i.evidence.quote}"` : ''}>
                <td>{label(i.ingredient_id)}</td>
                <td className="r strong">{decimal(i.quantity, i.base_unit === 'each' ? 0 : 1)} {i.base_unit === 'each' ? '' : i.base_unit}</td>
                <td className="r">{money(i.unit_cost)}{i.base_unit === 'each' ? ' each' : `/${i.base_unit}`}</td>
                <td className="r">{money(i.cost)}</td>
              </tr>)}</tbody>
              {snapshot.metrics.find((m) => m.id === 'forecast.ingredient_cost')?.value && <tfoot><tr className="strong"><td colSpan={3} className="r">Total</td><td className="r">{money(snapshot.metrics.find((m) => m.id === 'forecast.ingredient_cost')!.value)}</td></tr></tfoot>}
            </table></div>
          </div>
          <div className="table-scroll"><table className="tbl">
            <caption>Demand sensitivity scenarios — not prediction intervals</caption>
            <thead><tr><th>Scenario</th><th className="r">Units</th><th className="r">Net revenue</th><th className="r">Ingredient consumption cost</th></tr></thead>
            <tbody>{snapshot.scenarios.map((s) => <tr key={s.name}><td>{label(s.name)}</td><td className="r">{decimal(s.units, 1)}</td><td className="r">{money(s.revenue)}</td><td className="r">{money(s.ingredient_cost)}</td></tr>)}</tbody>
          </table></div>
          {snapshot.evaluation?.weekday_average_mae != null && <p className="hint">Seven-day holdout MAE: {decimal(snapshot.evaluation.weekday_average_mae, 2)} units per dish/channel/day; previous-week baseline: {decimal(snapshot.evaluation.seasonal_naive_mae, 2)}. {snapshot.evaluation.status !== 'ready' ? 'Partial evaluation sample. ' : ''}Synthetic demo results do not establish real-world accuracy.</p>}
        </>}
        {snapshot.limitations.length > 0 && <details className="assume" open={!ready}><summary>Planning limitations</summary><ul>{snapshot.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details>}
        <details className="assume"><summary>Method and assumptions</summary><p>{snapshot.method.replaceAll('_', ' ')} · data version {snapshot.source_data_version}</p><ul>{snapshot.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
      </>}
    </Card>
  );
}
