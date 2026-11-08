import type { ReactNode } from 'react';
import type { DocumentStatus } from '../marginguard-api';

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
