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
          <div className="table-scroll"><table className="tbl">
            <caption>Demand sensitivity scenarios — not prediction intervals</caption>
            <thead><tr><th>Scenario</th><th className="r">Units</th><th className="r">Net revenue</th><th className="r">Ingredient consumption cost</th></tr></thead>
            <tbody>{snapshot.scenarios.map((s) => <tr key={s.name}><td>{label(s.name)}</td><td className="r">{decimal(s.units, 1)}</td><td className="r">{money(s.revenue)}</td><td className="r">{money(s.ingredient_cost)}</td></tr>)}</tbody>
          </table></div>
          <details className="assume"><summary>Ingredient requirements and invoice evidence</summary>
            <div className="table-scroll"><table className="tbl"><thead><tr><th>Ingredient</th><th className="r">Required</th><th className="r">Unit price</th><th className="r">Consumption cost</th></tr></thead>
              <tbody>{snapshot.ingredients.map((i) => <tr key={i.ingredient_id} title={i.evidence.quote ?? ''}><td>{label(i.ingredient_id)}</td><td className="r">{decimal(i.quantity, 2)} {i.base_unit}</td><td className="r">{money(i.unit_cost)}</td><td className="r">{money(i.cost)}</td></tr>)}</tbody></table></div>
          </details>
          {snapshot.evaluation?.weekday_average_mae != null && <p className="hint">Seven-day holdout MAE: {decimal(snapshot.evaluation.weekday_average_mae, 2)} units per dish/channel/day; previous-week baseline: {decimal(snapshot.evaluation.seasonal_naive_mae, 2)}. {snapshot.evaluation.status !== 'ready' ? 'Partial evaluation sample. ' : ''}Synthetic demo results do not establish real-world accuracy.</p>}
        </>}
        {snapshot.limitations.length > 0 && <details className="assume" open={!ready}><summary>Planning limitations</summary><ul>{snapshot.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details>}
        <details className="assume"><summary>Method and assumptions</summary><p>{snapshot.method.replaceAll('_', ' ')} · data version {snapshot.source_data_version}</p><ul>{snapshot.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
      </>}
    </Card>
  );
}
