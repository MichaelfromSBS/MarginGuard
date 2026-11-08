import { useEffect, useRef, useState } from 'react';
import type { ForecastResponse, ForecastMethod, PricingScenarioResponse } from '../marginguard-api';
import { api, errorText } from './client';
import { decimal, label, money, shortDate } from './format';
import { MetricCard } from './Metrics';
import { Card, Empty, ErrorBox, Pill } from './ui';
import ForecastChart from './ForecastChart';

export default function Forecast({ snapshot, onChanged }: { snapshot: ForecastResponse | null; onChanged: (forecast: ForecastResponse) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [method, setMethod] = useState<ForecastMethod>(() => snapshot?.method as ForecastMethod ?? 'adaptive_ensemble_v1');
  const inFlight = useRef(false);
  const attempted = useRef('');
  const changed = useRef(onChanged);
  changed.current = onChanged;
  useEffect(() => { if (snapshot?.method && !inFlight.current) setMethod(snapshot.method as ForecastMethod); }, [snapshot?.method]);
  const calculate = async (selected?: ForecastMethod) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const result = await api.recalculate(selected ? { method: selected } : {});
      if (selected && result.method !== selected) throw new Error('The server returned a different forecast model. Restart the API and try again.');
      changed.current(result);
    }
    catch (e) { setError(errorText(e)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  useEffect(() => {
    if (snapshot && snapshot.status !== 'pending') return;
    const key = snapshot ? `${snapshot.id}:${snapshot.status}:${snapshot.source_data_version}` : 'initial';
    if (attempted.current === key || inFlight.current) return;
    attempted.current = key;
    // Automatic refresh uses the server's stored policy. Only a user selection
    // sends an explicit method; an old snapshot must never force a model reset.
    void calculate();
  }, [snapshot?.id, snapshot?.status, snapshot?.source_data_version, busy]);
  const adaptive = snapshot?.model_metadata?.adaptive as { selection: { dish_id: string; channel_id: string; lead_days: number[]; weights: Record<string, number>; observations: number; reason: string }[] } | undefined;
  const ready = snapshot?.status === 'ready';
  return (
    <Card title="Next-month outlook" action={<span className="hint" role="status">{busy ? 'Updating forecast…' : 'Updates automatically'}</span>}>
      <label className="forecast-method">Demand model <select aria-label="Demand model" value={method} disabled={busy} onChange={(e) => { const next = e.target.value as ForecastMethod; setMethod(next); void calculate(next); }}>
        <option value="adaptive_ensemble_v1">Auto · adaptive ensemble (default)</option>
        <option value="recency_weekday_v1">Recent weekday trends</option>
        <option value="weekday_average_v1">Weekday average</option>
        <option value="regularized_poisson_v1">Regularized Poisson (experimental ML)</option>
        <option value="poisson_gradient_boosting_v1">Poisson gradient boosting (experimental ML)</option>
      </select></label>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!snapshot && <Empty>Preparing your forecast…</Empty>}
      {snapshot && <>
        <p className="muted">{shortDate(snapshot.horizon.start)} – {shortDate(snapshot.horizon.end)} · <Pill tone={ready ? 'ok' : 'warn'}>{snapshot.status === 'pending' ? 'Out of date' : label(snapshot.status)}</Pill></p>
        {snapshot.status === 'pending' && <div className="issues">Records changed. Updating the forecast automatically…</div>}
        {snapshot.status === 'pending' && snapshot.daily.length > 0 && snapshot.daily.every((day) => day.units !== null) && <ForecastChart snapshot={snapshot} scenario={null} updating stale />}
        {snapshot.status === 'insufficient_history' && <Empty>More sales history or planning inputs needed.</Empty>}
        {ready && <>
          <div className="metrics">{snapshot.metrics.map((m) => <MetricCard key={m.id} m={m} />)}</div>
          <PricingPlanner snapshot={snapshot} />
          <div className="subsection">
            <h4>Ingredients needed next month</h4>
            <p className="hint">Expected usage at current prices; excludes stock on hand.</p>
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
            <caption title="Sensitivity scenarios, not prediction intervals">Volume scenarios</caption>
            <thead><tr><th>Scenario</th><th className="r">Units</th><th className="r">Net revenue</th><th className="r">Ingredient cost</th></tr></thead>
            <tbody>{snapshot.scenarios.map((s) => <tr key={s.name}><td>{label(s.name)}</td><td className="r">{decimal(s.units, 1)}</td><td className="r">{money(s.revenue)}</td><td className="r">{money(s.ingredient_cost)}</td></tr>)}</tbody>
          </table></div>
          {snapshot.evaluation?.weekday_average_mae != null && <details className="assume"><summary>Forecast accuracy</summary><p className="hint">Seven-day holdout MAE: selected model {decimal(snapshot.evaluation.selected_method_mae ?? snapshot.evaluation.weekday_average_mae, 2)} units per dish/channel/day; weekday average {decimal(snapshot.evaluation.weekday_average_mae, 2)}; previous-week baseline: {decimal(snapshot.evaluation.seasonal_naive_mae, 2)}. {snapshot.evaluation.status !== 'ready' ? 'Partial evaluation sample. ' : ''}Demo results do not establish real-world accuracy.</p></details>}
        </>}
        {snapshot.limitations.length > 0 && <details className="assume" open={!ready}><summary>Planning limitations</summary><ul>{snapshot.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details>}
        {adaptive && <details className="assume"><summary>Adaptive model mix</summary><div className="table-scroll"><table className="tbl"><thead><tr><th>Dish / channel</th><th>Days ahead</th><th>Model weights</th><th className="r">Scored cases</th></tr></thead><tbody>{adaptive.selection.map((s) => <tr key={`${s.dish_id}/${s.channel_id}/${s.lead_days[0]}`} title={label(s.reason)}><td>{label(s.dish_id)} / {label(s.channel_id)}</td><td>{s.lead_days.join('–')}</td><td>{Object.entries(s.weights).map(([name, weight]) => `${label(name.replace('_v1', ''))} ${Math.round(weight * 100)}%`).join(' · ')}</td><td className="r">{s.observations}</td></tr>)}</tbody></table></div></details>}
        <details className="assume"><summary>Method and assumptions</summary><p>{snapshot.method.replaceAll('_', ' ')} · data version {snapshot.source_data_version}</p><ul>{snapshot.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
      </>}
    </Card>
  );
}

function PricingPlanner({ snapshot }: { snapshot: ForecastResponse }) {
  const [ingredient, setIngredient] = useState(snapshot.ingredients[0]?.ingredient_id ?? '');
  const [price, setPrice] = useState('');
  const [passThrough, setPassThrough] = useState('100');
  const [elasticity, setElasticity] = useState('-1');
  const [reference, setReference] = useState('');
  const [result, setResult] = useState<PricingScenarioResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selected = snapshot.ingredients.find((i) => i.ingredient_id === ingredient);
  const [resultKey, setResultKey] = useState('');
  const inputs = JSON.stringify([snapshot.id, ingredient, price, passThrough, elasticity, reference]);
  const currentResult = resultKey === inputs ? result : null;
  const decimalInput = (value: string, signed = false) => (signed ? /^-?(0|[1-9]\d*)(\.\d{1,8})?$/ : /^(0|[1-9]\d*)(\.\d{1,8})?$/).test(value);
  const valid = decimalInput(passThrough) && Number(passThrough) <= 100
    && decimalInput(elasticity, true) && Number(elasticity) >= -5 && Number(elasticity) <= 0
    && (price === '' || (decimalInput(price) && Number(price) <= 1000000))
    && (reference === '' || (/^\d{4}-\d{2}-\d{2}$/.test(reference) && reference >= '1900-01-01' && reference <= (snapshot.as_of ?? '9999-12-31')));
  useEffect(() => {
    setError('');
    if (!valid) { setBusy(false); return; }
    const controller = new AbortController();
    let active = true;
    setBusy(true);
    const timer = window.setTimeout(async () => {
      try {
        const value = await api.pricingScenario(snapshot.id, {
          reference_date: reference || undefined, cost_pass_through_pct: passThrough, price_elasticity: elasticity,
          ingredient_prices: price === '' ? [] : [{ ingredient_id: ingredient, unit_cost: price }],
        }, controller.signal);
        if (active) { setResult(value); setResultKey(inputs); }
      } catch (e) { if (active && !controller.signal.aborted) setError(errorText(e)); }
      finally { if (active) setBusy(false); }
    }, 350);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [inputs, valid]);
  return <div className="subsection pricing-planner">
    <ForecastChart snapshot={snapshot} scenario={currentResult} updating={busy || (valid && !currentResult && !error)} />
    <h4>Ingredient prices → menu prices → demand</h4>
    <p className="hint">Preview price changes without changing your menu.</p>
    <form onSubmit={(event) => event.preventDefault()}>
      <fieldset className="pricing-controls">
        <label>Ingredient<select aria-label="Ingredient" value={ingredient} onChange={(e) => { setIngredient(e.target.value); setPrice(''); }}>{snapshot.ingredients.map((i) => <option key={i.ingredient_id} value={i.ingredient_id}>{label(i.ingredient_id)}</option>)}</select></label>
        <label>Future price per {selected?.base_unit ?? 'unit'} (optional)<input aria-label="Future ingredient price" type="number" min="0" max="1000000" step="0.00000001" placeholder={selected?.unit_cost ?? ''} value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <label>Pass cost change to customers (%)<input type="number" required min="0" max="100" step="0.1" value={passThrough} onChange={(e) => setPassThrough(e.target.value)} /></label>
        <label>Assumed price elasticity<input type="number" required min="-5" max="0" step="0.1" value={elasticity} onChange={(e) => setElasticity(e.target.value)} /></label>
        <label>Cost comparison date (optional)<input type="date" min="1900-01-01" max={snapshot.as_of ?? undefined} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
      </fieldset>
    </form>
    <p className="hint">Price sensitivity is assumed. <span title="100% passes through cost changes in dollars. Costs compare with 28 days earlier by default.">0% keeps menu prices fixed.</span></p>
    {!valid && <p className="issues">Enter valid prices, pass-through from 0–100%, elasticity from −5 to 0, and a comparison date no later than the forecast date.</p>}
    <p className="hint" role="status">{busy ? 'Updating pricing scenario…' : currentResult ? 'Up to date' : 'Auto-updating'}</p>
    {error && <ErrorBox>{error}</ErrorBox>}
    {currentResult && <div aria-live="polite">
      <p><Pill tone="warn">What-if · assumed price sensitivity</Pill> · reference {shortDate(currentResult.reference_date)}</p>
      <div className="table-scroll"><table className="tbl"><caption>Pricing outlook</caption>
        <thead><tr><th>Measure</th><th className="r">Current-menu forecast</th><th className="r">Pricing scenario</th></tr></thead>
        <tbody><tr><td>Units</td><td className="r">{decimal(snapshot.metrics.find((m) => m.id === 'forecast.units')?.value, 1)}</td><td className="r">{decimal(currentResult.units, 1)}</td></tr>
          <tr><td>Revenue</td><td className="r">{money(snapshot.metrics.find((m) => m.id === 'forecast.revenue')?.value)}</td><td className="r">{money(currentResult.revenue)}</td></tr>
          <tr><td>Ingredient cost</td><td className="r">{money(snapshot.metrics.find((m) => m.id === 'forecast.ingredient_cost')?.value)}</td><td className="r">{money(currentResult.ingredient_cost)}</td></tr></tbody>
      </table></div>
      <div className="table-scroll"><table className="tbl"><thead><tr><th>Dish / channel</th><th className="r">Reference → scenario ingredient cost</th><th className="r">Menu price</th><th className="r">Demand</th></tr></thead>
        <tbody>{currentResult.series.map((s) => <tr key={`${s.dish_id}/${s.channel_id}`}><td>{label(s.dish_id)} / {label(s.channel_id)}</td><td className="r">{money(s.reference_unit_cost)} → {money(s.scenario_unit_cost)}</td><td className="r">{money(s.current_menu_price)} → {money(s.scenario_menu_price)}</td><td className="r">{decimal(s.baseline_units, 1)} → {decimal(s.units, 1)}</td></tr>)}</tbody>
      </table></div>
      <details className="assume"><summary>Scenario ingredient needs and assumptions</summary>
        <ul>{currentResult.ingredients.map((i) => <li key={i.ingredient_id}>{label(i.ingredient_id)}: {decimal(i.quantity, 2)} {i.base_unit} at {money(i.unit_cost)}/{i.base_unit} ({label(i.price_source)})</li>)}</ul>
        <ul>{[...currentResult.assumptions, ...currentResult.limitations].map((a) => <li key={a}>{a}</li>)}</ul>
      </details>
    </div>}
  </div>;
}
