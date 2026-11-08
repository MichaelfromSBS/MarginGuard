import { useEffect, useRef, useState } from 'react';
import type { ForecastResponse, PricingScenarioResponse } from '../marginguard-api';
import { decimal, money, shortDate } from './format';
import { Empty } from './ui';

type Measure = 'units' | 'revenue' | 'ingredient_cost';
const MEASURES: Record<Measure, string> = { units: 'Dishes sold', revenue: 'Revenue', ingredient_cost: 'Ingredient cost' };
const MODELS: Record<string, string> = { adaptive_ensemble_v1: 'Auto ensemble', weekday_average_v1: 'Weekday average', recency_weekday_v1: 'Recent trends', regularized_poisson_v1: 'Poisson regression', poisson_gradient_boosting_v1: 'Gradient boosting' };
export interface ForecastPoint { date: string; baseline: number; scenario: number | null }

/** Display-only daily allocation. The backend's Decimal monthly totals remain authoritative. */
export function forecastPoints(snapshot: ForecastResponse, scenario: PricingScenarioResponse | null, measure: Measure): ForecastPoint[] {
  const series = new Map(snapshot.series.map((s) => [`${s.dish_id}/${s.channel_id}`, s]));
  const adjustments = new Map((scenario?.series ?? []).map((s) => [`${s.dish_id}/${s.channel_id}`, s]));
  const days = new Map<string, ForecastPoint>();
  for (const day of snapshot.daily) {
    const source = series.get(`${day.dish_id}/${day.channel_id}`);
    if (!source || day.units === null) continue;
    const changed = adjustments.get(`${day.dish_id}/${day.channel_id}`);
    const point = days.get(day.date) ?? { date: day.date, baseline: 0, scenario: scenario ? 0 : null };
    const units = Number(day.units);
    const total = Number(source.units);
    const baseValue = measure === 'units' ? 1 : measure === 'revenue' ? Number(source.menu_price) : total > 0 ? Number(source.ingredient_cost) / total : 0;
    point.baseline += units * baseValue;
    if (scenario && changed) {
      const ratio = total > 0 ? Number(changed.units) / total : 0;
      const changedValue = measure === 'units' ? 1 : Number(measure === 'revenue' ? changed.scenario_menu_price : changed.scenario_unit_cost);
      point.scenario = (point.scenario ?? 0) + units * ratio * changedValue;
    }
    days.set(day.date, point);
  }
  return [...days.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** Monotone cubic interpolation: passes through daily values without overshooting peaks/zeros. */
export function smoothPath(points: { x: number; y: number }[]): string {
  if (!points.length) return '';
  if (points.length === 1) return `M${points[0].x},${points[0].y}`;
  const slopes = points.slice(1).map((p, i) => (p.y - points[i].y) / (p.x - points[i].x));
  const tangents = points.map((_, i) => i === 0 ? slopes[0] : i === points.length - 1 ? slopes.at(-1)! :
    slopes[i - 1] * slopes[i] <= 0 ? 0 : 2 / (1 / slopes[i - 1] + 1 / slopes[i]));
  const n = (value: number) => value.toFixed(3);
  let path = `M${n(points[0].x)},${n(points[0].y)}`;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i], step = (b.x - a.x) / 3;
    path += ` C${n(a.x + step)},${n(a.y + tangents[i - 1] * step)} ${n(b.x - step)},${n(b.y - tangents[i] * step)} ${n(b.x)},${n(b.y)}`;
  }
  return path;
}

export default function ForecastChart({ snapshot, scenario, updating, stale = false }: { snapshot: ForecastResponse; scenario: PricingScenarioResponse | null; updating: boolean; stale?: boolean }) {
  const [measure, setMeasure] = useState<Measure>('units');
  const [hover, setHover] = useState<number | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(760);
  const scale = useRef<{ epoch: string; peaks: Partial<Record<Measure, number>> }>({ epoch: '', peaks: {} });
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.max(280, Math.round(entry.contentRect.width)));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const points = forecastPoints(snapshot, scenario, measure);
  const H = 270, L = 62, R = 16, T = 20, B = 34;
  const epoch = `${snapshot.source_data_version}:${snapshot.horizon.start}:${snapshot.horizon.end}`;
  if (scale.current.epoch !== epoch) scale.current = { epoch, peaks: {} };
  const peak = Math.max(1, scale.current.peaks[measure] ?? 0, ...points.flatMap((p) => [p.baseline, p.scenario ?? 0]));
  // Keep the same scale while comparing models on the same records/month.
  // Otherwise auto-scaling can make much lower predictions look identical.
  scale.current.peaks[measure] = peak;
  const max = Math.ceil(peak * 1.15 / (peak > 1000 ? 100 : peak > 100 ? 20 : 5)) * (peak > 1000 ? 100 : peak > 100 ? 20 : 5);
  const x = (index: number) => L + index / Math.max(1, points.length - 1) * (width - L - R);
  const y = (value: number) => T + (1 - value / max) * (H - T - B);
  const path = (key: 'baseline' | 'scenario') => smoothPath(points.map((p, i) => ({ x: x(i), y: y(p[key] ?? 0) })));
  const active = hover === null ? null : points[Math.min(hover, points.length - 1)];
  const activeIndex = active ? points.indexOf(active) : 0;
  const move = (event: React.PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = (event.clientX - bounds.left) / bounds.width * width;
    setHover(position < L || position > width - R ? null : Math.max(0, Math.min(points.length - 1, Math.round((position - L) / (width - L - R) * (points.length - 1)))));
  };
  const format = (value: number) => measure === 'units' ? decimal(value.toFixed(1), 1) : money(value.toFixed(2));
  const ticks = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])].filter((i) => i >= 0);
  const basePath = path('baseline'), scenarioPath = scenario ? path('scenario') : null;
  return <div className="forecast-visual" ref={container}>
    <div className="forecast-visual-head"><div><h3>{stale ? 'Previous forecast · updating' : 'Next month, day by day'}</h3><p className="hint">{shortDate(snapshot.horizon.start)} – {shortDate(snapshot.horizon.end)} · {MODELS[snapshot.method] ?? snapshot.method}</p></div>
      <div className="chips" role="group" aria-label="Forecast chart measure">{(Object.keys(MEASURES) as Measure[]).map((key) => <button type="button" key={key} className={`chip ${measure === key ? 'on' : ''}`} aria-pressed={measure === key} onClick={() => setMeasure(key)}>{MEASURES[key]}</button>)}</div>
    </div>
    <div className="forecast-legend"><span><i className="baseline" />{stale ? 'Previous forecast' : 'Current-menu forecast'}</span>{!stale && <span><i className="scenario" />Pricing scenario</span>}<span className="forecast-chart-status" role="status">{updating ? 'Updating…' : scenario ? 'Live scenario' : 'Current-menu forecast'}</span></div>
    <div className="forecast-hover-rail">
      {active && <div className="forecast-hover-cards" role="tooltip" style={{ left: `clamp(0px, calc(${x(activeIndex) / width * 100}% - 130px), max(0px, calc(100% - 260px)))` }}>
        <div className="forecast-hover-card current"><span>{stale ? 'Previous' : 'Current'} · {shortDate(active.date)}</span><strong>{format(active.baseline)}{measure === 'units' && <small> dishes</small>}</strong></div>
        {active.scenario !== null && <div className="forecast-hover-card scenario"><span>Scenario · {shortDate(active.date)}</span><strong>{format(active.scenario)}{measure === 'units' && <small> dishes</small>}</strong></div>}
      </div>}
    </div>
    <div className="forecast-plot">
    {points.length ? <svg className="forecast-chart" tabIndex={0} onPointerMove={move} onPointerLeave={() => setHover(null)}
      onFocus={() => setHover(0)} onBlur={() => setHover(null)} onKeyDown={(event) => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(event.key)) {
          event.preventDefault();
          setHover((current) => event.key === 'Escape' ? null : event.key === 'Home' ? 0 : event.key === 'End' ? points.length - 1 :
            Math.max(0, Math.min(points.length - 1, (current ?? 0) + (event.key === 'ArrowLeft' ? -1 : 1))));
        }
      }} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${stale ? 'Previous forecast, updating. ' : ''}Daily projected ${MEASURES[measure].toLowerCase()}, current-menu forecast${scenario ? ' compared with pricing scenario' : ''}`}>
      <desc>{`Daily projected ${MEASURES[measure].toLowerCase()}. Pricing effects use your assumed elasticity.`}</desc>
      {[0, 1, 2, 3].map((i) => { const v = max * i / 3; return <g key={i}><line className="grid" x1={L} x2={width - R} y1={y(v)} y2={y(v)} /><text className="axis" x={L - 10} y={y(v) + 4} textAnchor="end">{measure !== 'units' ? '$' : ''}{Math.round(v).toLocaleString('en-US')}</text></g>; })}
      {ticks.map((i) => <text className="axis" key={i} x={x(i)} y={H - 10} textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{shortDate(points[i].date)}</text>)}
      <path key={`base:${measure}:${basePath}`} className="forecast-stroke forecast-baseline" data-series="baseline" d={basePath} pathLength={1} />
      {scenarioPath && <path key={`scenario:${measure}:${scenarioPath}`} className="forecast-stroke forecast-scenario" data-series="scenario" d={scenarioPath} pathLength={1} />}
      {active && <g className="forecast-crosshair" aria-hidden="true" style={{ transform: `translateX(${x(activeIndex)}px)` }}>
        <line data-hover-date={active.date} x1={0} x2={0} y1={T} y2={H - B} />
        <circle className="base-marker" cx={0} cy={0} style={{ transform: `translateY(${y(active.baseline)}px)` }} r={4} />
        {active.scenario !== null && <circle className="scenario-marker" cx={0} cy={0} style={{ transform: `translateY(${y(active.scenario)}px)` }} r={4} />}
      </g>}
      <rect x={L} y={T} width={width - L - R} height={H - T - B} fill="transparent" />
    </svg> : <Empty>No daily forecast yet.</Empty>}
    </div>
    <details className="assume"><summary>View daily chart values</summary><div className="table-scroll"><table className="tbl"><thead><tr><th>Date</th><th className="r">Current menu</th><th className="r">Pricing scenario</th></tr></thead><tbody>{points.map((p) => <tr key={p.date}><td>{shortDate(p.date)}</td><td className="r">{format(p.baseline)}</td><td className="r">{p.scenario !== null ? format(p.scenario) : '—'}</td></tr>)}</tbody></table></div><p className="hint">Daily values are display estimates. Monthly totals use exact decimal arithmetic.</p></details>
  </div>;
}
