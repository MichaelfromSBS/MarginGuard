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
const files = { format: 'format.ts', client: 'client.ts', ui: 'ui.tsx', Metrics: 'Metrics.tsx', Forecast: 'Forecast.tsx' };
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
};
const render = (value) => renderToStaticMarkup(createElement(Forecast, { snapshot: value, onChanged() {} }));

test('a stale forecast cannot display its old totals as a current forecast', () => {
  const html = render({ ...snapshot, status: 'pending' });
  assert.match(html, /Out of date/);
  assert.match(html, /Recalculate forecast/);
  assert.doesNotMatch(html, /9,413\.63/);
});

test('ready forecasts display totals and label sensitivity scenarios', () => {
  const html = render(snapshot);
  assert.match(html, /9,413\.63/);
  assert.match(html, /not prediction intervals/);
});

test('empty and insufficient forecasts give an explicit next step', () => {
  assert.match(render(null), /Calculate forecast/);
  const html = render({ ...snapshot, status: 'insufficient_history', limitations: ['Need four complete weekdays.'] });
  assert.match(html, /Need four complete weekdays/);
  assert.doesNotMatch(html, /9,413\.63/);
});
