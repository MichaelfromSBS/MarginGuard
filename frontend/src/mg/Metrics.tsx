import type { Metric } from '../marginguard-api';
import { decimal, label, money, shortDate } from './format';
import { Pill } from './ui';

export function formatMetric(m: Metric) {
  if (m.value === null) return '—';
  if (m.unit === 'USD') return money(m.value);
  if (m.unit === 'percent') return `${decimal(m.value, 1)}%`;
  if (['lb', 'oz', 'each'].includes(m.unit)) return `${decimal(m.value, 1)} ${m.unit}`;
  return decimal(m.value, 0);
}

/** Plain-language names for the backend's precise metric labels (hover a card to see the original). */
const NAMES: Record<string, [string, string?]> = {
  'sales.units': ['Dishes sold'],
  'sales.orders': ['Orders'],
  'sales.net_revenue': ['Net sales', 'Food only, excluding tax and tips'],
  'sales.average_order_revenue': ['Average order value', 'Net sales ÷ orders'],
  'forecast.units': ['Projected dishes sold'],
  'forecast.revenue': ['Projected net sales', 'Food only, excluding tax and tips'],
  'forecast.ingredient_cost': ['Projected ingredient cost', 'Ingredients needed for projected sales, at today’s prices'],
};

export function displayName(m: Metric): [string, string | undefined] {
  const known = NAMES[m.id];
  if (known) return [known[0], known[1]];
  const dish = /^dish\.(.+)\.ingredient_cost$/.exec(m.id);
  if (dish) {
    const name = m.label.replace(/\s*replacement ingredient cost\s*$/i, '');
    return [`${name}: restock cost per dish`, 'Ingredients for one dish at today’s supplier prices'];
  }
  return [m.label.replace(/^Observed\s+/i, '').replace(/replacement/gi, 'restock'), undefined];
}

/** Sales figures need no badge; modeled and projected figures say how they were produced. */
const KIND: Partial<Record<Metric['kind'], [string, 'info' | 'accent']>> = { projected: ['Projected', 'accent'] };

export function MetricCard({ m }: { m: Metric }) {
  const [name, hint] = displayName(m);
  const badge = KIND[m.kind];
  return <div className="metric" title={m.label}>
    <div className="metric-top"><span>{name}</span>{badge && <Pill tone={badge[1]}>{badge[0]}</Pill>}</div>
    <div className="metric-value">{formatMetric(m)}</div>
    <div className="metric-foot">
      {m.period ? `${shortDate(m.period.start)} – ${shortDate(m.period.end)}` : hint ?? ''}
      {m.coverage !== 'complete' && <Pill tone="warn">{label(m.coverage)} data</Pill>}
    </div>
    {m.period && hint && <div className="metric-hint">{hint}</div>}
  </div>;
}
