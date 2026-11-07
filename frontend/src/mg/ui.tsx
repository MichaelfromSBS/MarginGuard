import type { ReactNode } from 'react';
import type { DocumentStatus } from '../marginguard-api';
import { shortDate } from './format';

export function Card({ title, action, children, className = '' }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && <div className="card-head"><h2>{title}</h2>{action}</div>}
      {children}
    </section>
  );
}

const STATUS: Record<DocumentStatus, [string, string]> = {
  detected: ['Queued', 'info'], processing: ['Reading…', 'info'], completed: ['Completed', 'ok'],
  needs_review: ['Needs review', 'warn'], failed: ['Failed', 'bad'],
};
export function StatusBadge({ status }: { status: DocumentStatus }) {
  const [text, tone] = STATUS[status];
  return <span className={`badge ${tone}`}>{(status === 'processing' || status === 'detected') && <i className="pulse" />}{text}</span>;
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'ok' | 'warn' | 'bad' | 'info' | 'accent' }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function NotYet({ checkpoint, what }: { checkpoint: number; what: string }) {
  return (
    <div className="notyet">
      <span className="notyet-tag">Checkpoint {checkpoint}</span>
      <p>{what} will appear here once the backend enables it.</p>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="errorbox">{children}</div>;
}

/** Step chart: a price holds until the next invoice changes it. */
export function PriceChart({ points, unit }: { points: { date: string; value: number; ref: string }[]; unit: string }) {
  if (points.length === 0) return <Empty>No prices recorded yet.</Empty>;
  const W = 1080, H = 280, L = 62, R = 24, T = 30, B = 34;
  const t = points.map((p) => new Date(`${p.date}T12:00:00Z`).getTime());
  const t0 = Math.min(...t), t1 = Math.max(...t) || t0 + 1;
  const vals = points.map((p) => p.value);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo || hi || 1) * 0.35;
  lo = Math.max(0, lo - pad); hi = hi + pad;
  const x = (ms: number) => L + ((ms - t0) / Math.max(1, t1 - t0)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let path = `M ${x(t[0])} ${y(vals[0])}`;
  for (let i = 1; i < points.length; i++) path += ` H ${x(t[i])} V ${y(vals[i])}`;
  const ticks = [...new Set(vals.map((v) => v.toFixed(2)))].map(Number).slice(-4);
  const dateTicks = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  const last = points.length - 1;
  const rising = points.length > 1 && vals[last] > vals[last - 1];
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Price history chart">
      {ticks.map((v) => (
        <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" />
          <text x={L - 8} y={y(v) + 4} textAnchor="end" className="axis">${v.toFixed(2)}</text></g>
      ))}
      {dateTicks.map((i) => <text key={i} x={x(t[i])} y={H - 10} textAnchor="middle" className="axis">{shortDate(points[i].date)}</text>)}
      <path d={path} className="line" />
      {points.map((p, i) => (
        <circle key={p.ref + i} cx={x(t[i])} cy={y(p.value)} r={i === last ? 5.5 : 3.5} className={i === last && rising ? 'dot hot' : 'dot'}>
          <title>{`${shortDate(p.date)}: $${p.value.toFixed(2)}/${unit}`}</title>
        </circle>
      ))}
      <text x={Math.min(x(t[last]), W - R - 4)} y={y(vals[last]) - 12} textAnchor="end" className={rising ? 'callout hot' : 'callout'}>
        ${vals[last].toFixed(2)}/{unit}
      </text>
    </svg>
  );
}
