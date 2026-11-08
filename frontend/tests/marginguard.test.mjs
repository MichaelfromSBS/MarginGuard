import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { transformWithOxc } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

// Compile the actual components for server rendering without launching Vite's
// native dependency optimizer or a second development server in the test suite.
const require = createRequire(import.meta.url);
const files = { format: 'format.ts', client: 'client.ts', ui: 'ui.tsx', Metrics: 'Metrics.tsx', ForecastChart: 'ForecastChart.tsx', PriceChart: 'PriceChart.tsx', Forecast: 'Forecast.tsx', useAlerts: 'useAlerts.ts', Alerts: 'Alerts.tsx' };
const urls = new Map();
async function moduleUrl(name) {
  if (urls.has(name)) return urls.get(name);
  const file = new URL(`../src/mg/${files[name]}`, import.meta.url);
  const source = readFileSync(file, 'utf8');
  const compiled = await transformWithOxc(source, fileURLToPath(file), { jsx: { runtime: 'automatic' } });
  let code = compiled.code;
  for (const match of compiled.code.matchAll(/from\s+(['"])([^'"]+)\1/g)) {
    const specifier = match[2];
    const url = specifier.startsWith('.') ? await moduleUrl(specifier.split('/').at(-1)) : pathToFileURL(require.resolve(specifier)).href;
    code = code.replace(match[0], `from ${JSON.stringify(url)}`);
  }
  const url = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
  urls.set(name, url);
  return url;
}
const format = await import(await moduleUrl('format'));
const { default: Forecast } = await import(await moduleUrl('Forecast'));
const { default: PriceChart, priceHistory, priceAtDate } = await import(await moduleUrl('PriceChart'));
const { forecastPoints, smoothPath } = await import(await moduleUrl('ForecastChart'));
const { updateAlertList } = await import(await moduleUrl('useAlerts'));
const { alertPreview, AlertItem } = await import(await moduleUrl('Alerts'));

const finding = {
  id: 'cost-1', type: 'projected_cost_increase', status: 'new', severity: 'warning',
  title: 'Ingredient increases raise next-month cost', message: 'A full measured explanation with assumptions.',
  created_at: '2026-11-08T12:00:00Z', evidence: [], suggestion: 'Compare supplier quotes.',
  finding: { increase: '730.17', changes: [{ ingredient_name: 'Ground beef', increase_pct: '18' }, { ingredient_name: 'Buns', increase_pct: '-5' }] },
};

test('saving and resolving keep feed counts correct, idempotent and independent of page size', () => {
  const initial = { items: [finding], newCount: 135, savedCount: 7 };
  const saved = { ...finding, status: 'acknowledged' };
  const updated = updateAlertList(initial, saved);
  assert.equal(updated.newCount, 134);
  assert.equal(updated.savedCount, 8);
  assert.equal(updated.items[0].status, 'acknowledged');
  assert.equal(initial.items[0].status, 'new');
  assert.deepEqual(updateAlertList(updated, saved), updated);
  const resolved = updateAlertList(updated, { ...saved, status: 'resolved' });
  assert.equal(resolved.items.length, 0);
  assert.equal(resolved.newCount, 134);
  assert.equal(resolved.savedCount, 7);
  assert.deepEqual(updateAlertList(resolved, { ...saved, status: 'resolved' }), resolved);
});

test('alert previews use measured causes and keep the complete explanation available', () => {
  assert.equal(alertPreview(finding), '+$730.17 projected ingredient cost · Ground beef +18%');
  const unusual = { ...finding, type: 'unusual_sales', finding: { date: '2026-11-07', drop_pct: '37.666', net_revenue: '487.90' } };
  assert.equal(alertPreview(unusual), 'Nov 7 · 37.7% fewer dishes than the weekday baseline · $487.90 net sales');
  assert.ok(alertPreview({ ...finding, finding: {}, message: 'Unusual values '.repeat(40) }).length <= 140);
  const html = renderToStaticMarkup(createElement(AlertItem, { a: finding, onChanged() {} }));
  assert.match(html, /Save for later/);
  assert.doesNotMatch(html, /Acknowledge|>Resolve</);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /class="notification-detail" hidden/);
  assert.match(html, /A full measured explanation with assumptions/);
  const saved = renderToStaticMarkup(createElement(AlertItem, { a: { ...finding, status: 'acknowledged' }, inbox: true, onChanged() {} }));
  assert.match(saved, />Saved</);
  assert.match(saved, />Resolve</);
  assert.doesNotMatch(saved, /Save for later/);
});

test('receipt discounts and monetary rounding preserve decimal precision', () => {
  assert.equal(format.money(format.subtractDecimal('37.00', '2.50')), '$34.50');
  assert.equal(format.subtractDecimal('100000000000000000.00000001', '0.00000001'), '100000000000000000');
  assert.equal(format.money('1.005'), '$1.01');
  assert.equal(format.money('-1.005'), '-$1.01');
  assert.equal(format.money(null), '—');
  assert.equal(format.localDate('2026-11-08T04:30:00Z'), '2026-11-07');
});

const snapshot = {
  status: 'ready', horizon: { start: '2026-12-01', end: '2026-12-31' },
  method: 'weekday_average_v1', source_data_version: 1,
  metrics: [{ id: 'forecast.ingredient_cost', label: 'Projected ingredient consumption cost', value: '9413.63',
    unit: 'USD', kind: 'projected', coverage: 'complete', period: { start: '2026-12-01', end: '2026-12-31' } }],
  limitations: [], assumptions: [], scenarios: [], ingredients: [], evaluation: null,
  series: [{ dish_id: 'burger', channel_id: 'in_store', units: '30', revenue: '360', ingredient_cost: '90', menu_price: '12' }],
  daily: [{ date: '2026-12-01', dish_id: 'burger', channel_id: 'in_store', is_open: true, units: '10' },
    { date: '2026-12-02', dish_id: 'burger', channel_id: 'in_store', is_open: true, units: '20' }],
};
const render = (value) => renderToStaticMarkup(createElement(Forecast, { snapshot: value, onChanged() {} }));

test('a stale forecast cannot display its old totals as a current forecast', () => {
  const html = render({ ...snapshot, status: 'pending' });
  assert.match(html, /Out of date/);
  assert.match(html, /Updating the forecast automatically/);
  assert.doesNotMatch(html, /<button[^>]*>Recalculate/);
  assert.doesNotMatch(html, /9,413\.63/);
});

test('ready forecasts display totals and label sensitivity scenarios', () => {
  const html = render(snapshot);
  assert.match(html, /9,413\.63/);
  assert.match(html, /not prediction intervals/);
  assert.match(html, /experimental ML/);
  assert.match(html, /Daily projected dishes sold/);
  assert.match(html, /Auto-updating/);
  assert.doesNotMatch(html, /<button[^>]*>Explore pricing/);
  assert.match(html, /Price sensitivity is assumed/);
  assert.match(html, /0% keeps menu prices fixed/);
});

test('empty and insufficient forecasts give an explicit next step', () => {
  assert.match(render(null), /Preparing your forecast/);
  const html = render({ ...snapshot, status: 'insufficient_history', limitations: ['Need four complete weekdays.'] });
  assert.match(html, /Need four complete weekdays/);
  assert.doesNotMatch(html, /9,413\.63/);
});

test('daily chart allocations preserve series shape and reflect pricing assumptions', () => {
  const scenario = { series: [{ dish_id: 'burger', channel_id: 'in_store', baseline_units: '30', units: '24', scenario_menu_price: '15', scenario_unit_cost: '4' }] };
  const demand = forecastPoints(snapshot, scenario, 'units');
  assert.deepEqual(demand.map((p) => p.scenario), [8, 16]);
  assert.deepEqual(demand.map((p) => p.baseline), [10, 20]);
  assert.equal(forecastPoints(snapshot, scenario, 'revenue').reduce((sum, p) => sum + p.scenario, 0), 360);
  assert.equal(forecastPoints(snapshot, scenario, 'ingredient_cost').reduce((sum, p) => sum + p.scenario, 0), 96);
  assert.equal(forecastPoints(snapshot, null, 'units')[0].scenario, null);
});

test('zero-volume and closed days remain finite zeros in chart data', () => {
  const zero = { ...snapshot, series: snapshot.series.map((s) => ({ ...s, units: '0', ingredient_cost: '0' })), daily: snapshot.daily.map((d) => ({ ...d, units: '0', is_open: false })) };
  const scenario = { series: [{ dish_id: 'burger', channel_id: 'in_store', units: '0', scenario_menu_price: '12', scenario_unit_cost: '3' }] };
  assert.ok(forecastPoints(zero, scenario, 'ingredient_cost').every((p) => p.baseline === 0 && p.scenario === 0));
});


test('smooth curves use bounded cubic controls and preserve every daily point', () => {
  const points = [{ x: 0, y: 12 }, { x: 10, y: 2 }, { x: 20, y: 0 }, { x: 30, y: 15 }, { x: 40, y: 15 }];
  const path = smoothPath(points);
  assert.match(path, / C/);
  const segments = [...path.matchAll(/C([\d.-]+),([\d.-]+) ([\d.-]+),([\d.-]+) ([\d.-]+),([\d.-]+)/g)];
  assert.equal(segments.length, points.length - 1);
  segments.forEach((segment, i) => {
    const [_, x1, y1, x2, y2, x, y] = segment.map(Number);
    const low = Math.min(points[i].y, points[i + 1].y), high = Math.max(points[i].y, points[i + 1].y);
    assert.ok(y1 >= low && y1 <= high && y2 >= low && y2 <= high);
    assert.equal(x, points[i + 1].x); assert.equal(y, points[i + 1].y);
  });
  assert.equal(smoothPath([]), '');
  assert.equal(smoothPath([{ x: 1, y: 0 }]), 'M1,0');
});


test('supplier prices keep their effective value between recorded invoices', () => {
  const original = [{ date: '2026-11-07', value: 4.72, ref: 'new' }, { date: '2026-11-01', value: 4, ref: 'old' }];
  const sorted = priceHistory(original);
  assert.equal(original[0].ref, 'new');
  assert.equal(priceAtDate(sorted, '2026-10-31'), undefined);
  assert.equal(priceAtDate(sorted, '2026-11-06').value, 4);
  assert.equal(priceAtDate(sorted, '2026-11-07').value, 4.72);
  assert.equal(priceAtDate(sorted, '2026-11-20').value, 4.72);
  const html = renderToStaticMarkup(createElement(PriceChart, { points: original, unit: 'lb' }));
  assert.match(html, /Ingredient price history chart/);
  assert.match(html, / H .* V /);
  assert.match(html, /forecast-stroke/);
});

test('ingredient history handles one observation, repeated dates and zero prices', () => {
  const sameDay = [{ date: '2026-11-01', value: 4, ref: 'a' }, { date: '2026-11-01', value: 4.2, ref: 'b' }];
  assert.equal(priceHistory(sameDay).length, 1);
  assert.equal(priceHistory(sameDay)[0].ref, 'b');
  const zero = renderToStaticMarkup(createElement(PriceChart, { points: [{ date: '2026-11-01', value: 0, ref: 'z' }], unit: 'each' }));
  assert.doesNotMatch(zero, /NaN|Infinity/);
  assert.match(zero, /Latest \$0.00/);
  assert.match(renderToStaticMarkup(createElement(PriceChart, { points: [], unit: 'lb' })), /No prices recorded/);
});
