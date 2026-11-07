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
const KIND: Record<Metric['kind'], [string, 'ok' | 'info' | 'accent']> = { actual: ['Observed', 'ok'], modeled: ['Modeled', 'info'], projected: ['Projected', 'accent'] };

export function MetricCard({ m }: { m: Metric }) {
  return <div className="metric">
    <div className="metric-top"><span>{m.label}</span><Pill tone={KIND[m.kind][1]}>{KIND[m.kind][0]}</Pill></div>
    <div className="metric-value">{formatMetric(m)}</div>
    <div className="metric-foot">
      {m.period ? `${shortDate(m.period.start)} – ${shortDate(m.period.end)}` : ''}
      {m.coverage !== 'complete' && <Pill tone="warn">{label(m.coverage)} data</Pill>}
    </div>
  </div>;
}
