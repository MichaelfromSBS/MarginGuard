import { useEffect, useRef, useState } from 'react';
import { money, shortDate } from './format';
import { Empty } from './ui';

export interface PricePoint { date: string; value: number; ref: string }
const DAY = 86400000;

/** Stable date ordering; the last returned record on a date is its effective price. */
export function priceHistory(points: PricePoint[]): PricePoint[] {
  const values = new Map<string, PricePoint>();
  for (const point of [...points].sort((a, b) => a.date.localeCompare(b.date))) values.set(point.date, point);
  return [...values.values()];
}

export function priceAtDate(points: PricePoint[], date: string): PricePoint | undefined {
  let low = 0, high = points.length - 1, found = -1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (points[middle].date <= date) { found = middle; low = middle + 1; }
    else high = middle - 1;
  }
  return found < 0 ? undefined : points[found];
}

/** Recorded prices hold until another invoice; animation never invents intermediate costs. */
export default function PriceChart({ points: records, unit }: { points: PricePoint[]; unit: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(760);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.max(280, Math.round(entry.contentRect.width)));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const points = priceHistory(records);
  const H = 270, L = 62, R = 16, T = 20, B = 34;
  const start = points.length ? new Date(`${points[0].date}T00:00:00Z`).getTime() : 0;
  const end = points.length ? new Date(`${points.at(-1)!.date}T00:00:00Z`).getTime() : start;
  const lastDay = Math.max(0, Math.round((end - start) / DAY));
  const dateAt = (day: number) => new Date(start + day * DAY).toISOString().slice(0, 10);
  const x = (day: number) => L + day / Math.max(1, lastDay) * (width - L - R);
  const values = points.map((p) => p.value);
  const min = points.length ? Math.min(...values) : 0, max = points.length ? Math.max(...values) : 1;
  const pad = (max - min || max * .2 || 1) * .25;
  const lo = Math.max(0, min - pad), hi = max + pad;
  const y = (value: number) => T + (1 - (value - lo) / (hi - lo)) * (H - T - B);
  let path = '';
  if (points.length) {
    path = `M ${x(0)} ${y(points[0].value)}`;
    for (let i = 1; i < points.length; i++) {
      const day = Math.round((new Date(`${points[i].date}T00:00:00Z`).getTime() - start) / DAY);
      path += ` H ${x(day)} V ${y(points[i].value)}`;
    }
    if (lastDay === 0) path += ` H ${width - R}`;
  }
  const day = hover === null ? null : Math.min(hover, lastDay);
  const activeDate = day === null ? null : dateAt(day);
  const active = activeDate ? priceAtDate(points, activeDate) : undefined;
  const ticks = [...new Set([0, Math.floor(lastDay / 2), lastDay])];
  const latest = points.at(-1);
  return <div className="ingredient-chart" ref={container}>
    {latest ? <>
      <div className="forecast-legend"><span><i className="scenario" />Recorded supplier price</span><span className="forecast-chart-status">Latest {money(latest.value.toFixed(8))}/{unit}</span></div>
      <div className="forecast-hover-rail">
        {active && day !== null && <div className="forecast-hover-cards ingredient-readout" role="tooltip"
          style={{ left: `clamp(0px, calc(${x(day) / width * 100}% - 65px), max(0px, calc(100% - 130px)))` }}>
          <div className="forecast-hover-card scenario" title={`Invoice effective ${active.date}`}><span>{shortDate(activeDate!)}</span><strong>{money(active.value.toFixed(8))}<small>/{unit}</small></strong></div>
        </div>}
      </div>
      <svg className="forecast-chart ingredient-price-chart" viewBox={`0 0 ${width} ${H}`} role="img" aria-label="Ingredient price history chart" tabIndex={0}
        onPointerMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const position = (event.clientX - bounds.left) / bounds.width * width;
          setHover(position < L || position > width - R ? null : Math.max(0, Math.min(lastDay, Math.round((position - L) / (width - L - R) * lastDay))));
        }} onPointerLeave={() => setHover(null)} onFocus={() => setHover(0)} onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(event.key)) return;
          event.preventDefault();
          setHover((current) => event.key === 'Escape' ? null : event.key === 'Home' ? 0 : event.key === 'End' ? lastDay : Math.max(0, Math.min(lastDay, (current ?? 0) + (event.key === 'ArrowLeft' ? -1 : 1))));
        }}>
        <desc>Approved invoice prices. Each price holds until the next invoice.</desc>
        {[0, 1, 2, 3].map((i) => { const value = lo + (hi - lo) * i / 3; return <g key={i}><line className="grid" x1={L} x2={width - R} y1={y(value)} y2={y(value)} /><text className="axis" x={L - 10} y={y(value) + 4} textAnchor="end">{money(value.toFixed(8))}</text></g>; })}
        {ticks.map((i) => <text className="axis" key={i} x={x(i)} y={H - 10} textAnchor={i === 0 ? 'start' : i === lastDay ? 'end' : 'middle'}>{shortDate(dateAt(i))}</text>)}
        <path key={path} className="forecast-stroke ingredient-price-line" data-series="ingredient-price" d={path} pathLength={1} />
        {points.map((p) => { const index = Math.round((new Date(`${p.date}T00:00:00Z`).getTime() - start) / DAY); return <circle className="ingredient-invoice-dot" key={p.ref} cx={x(index)} cy={y(p.value)} r={3} />; })}
        {active && day !== null && <g className="forecast-crosshair" aria-hidden="true" style={{ transform: `translateX(${x(day)}px)` }}>
          <line data-price-hover-date={activeDate} x1={0} x2={0} y1={T} y2={H - B} />
          <circle className="scenario-marker" cx={0} cy={0} r={4} style={{ transform: `translateY(${y(active.value)}px)` }} />
        </g>}
        <rect x={L} y={T} width={width - L - R} height={H - T - B} fill="transparent" />
      </svg>
    </> : <Empty>No prices recorded yet.</Empty>}
  </div>;
}
