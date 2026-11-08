import { useEffect, useRef, useState } from 'react';
import type { Alert } from '../marginguard-api';
import type { AlertFeed } from './useAlerts';
import { api, errorText } from './client';
import { money, qty, shortDate, timeAgo } from './format';
import { Card, Empty, ErrorBox } from './ui';

const numeric = (value: unknown): value is string => typeof value === 'string' && /^-?\d+(?:\.\d+)?$/.test(value);
const compact = (text: string, limit = 140) => text.length <= limit ? text : `${text.slice(0, limit - 1).replace(/\s+\S*$/, '')}…`;

/** Short, deterministic readouts; the complete measured explanation stays in details. */
export function alertPreview(alert: Alert): string {
  const f = alert.finding;
  if (alert.type === 'projected_cost_increase' && numeric(f.increase)) {
    const causes = Array.isArray(f.changes) ? f.changes.filter((c) => c && typeof c === 'object' && numeric(c.increase_pct) && Number(c.increase_pct) > 0 && typeof c.ingredient_name === 'string') : [];
    const names = causes.slice(0, 2).map((c) => `${c.ingredient_name} +${qty(c.increase_pct)}%`).join(', ');
    return compact(`+${money(f.increase)} projected ingredient cost${names ? ` · ${names}${causes.length > 2 ? ` +${causes.length - 2} more` : ''}` : ''}`);
  }
  if (alert.type === 'unusual_sales' && numeric(f.drop_pct)) {
    const date = typeof f.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(f.date) ? `${shortDate(f.date)} · ` : '';
    return compact(`${date}${Number(f.drop_pct).toFixed(1)}% fewer dishes than the weekday baseline${numeric(f.net_revenue) ? ` · ${money(f.net_revenue)} net sales` : ''}`);
  }
  return compact(alert.message.replace(/\s+/g, ' ').trim());
}

function category(alert: Alert) { return alert.type === 'unusual_sales' ? 'Sales' : alert.type.includes('cost') || alert.type.includes('price') ? 'Costs' : 'Notice'; }

export function AlertItem({ a, inbox = false, onChanged, onOpenInbox, onSource, reveal = 0 }: {
  a: Alert; inbox?: boolean; onChanged: (a: Alert) => void; onOpenInbox?: (id: string) => void;
  onSource?: (id: string) => void; reveal?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState<'save' | 'resolve' | null>(null);
  const item = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!reveal) return;
    setExpanded(true);
    item.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    item.current?.querySelector<HTMLButtonElement>('.notification-toggle')?.focus({ preventScroll: true });
  }, [reveal]);
  const act = async (action: 'save' | 'resolve') => {
    setBusy(action); setErr('');
    try { onChanged(await (action === 'save' ? api.saveAlertForLater(a.id) : api.resolve(a.id))); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(null); }
  };
  const detailId = `alert-detail-${inbox ? 'inbox' : 'overview'}-${a.id}`;
  return <div ref={item} className={`notification ${a.severity} ${a.status === 'acknowledged' ? 'is-saved' : ''}`} data-alert-id={a.id}>
    <div className="notification-row">
      <button className="notification-toggle" aria-expanded={expanded} aria-controls={detailId} onClick={() => setExpanded(!expanded)}>
        <span className="notification-icon" aria-hidden="true">{a.type === 'unusual_sales' ? '↘' : a.type.includes('cost') || a.type.includes('price') ? '↗' : '!'}</span>
        <span className="notification-copy"><span className="notification-meta">{category(a)}<span>·</span>{timeAgo(a.created_at)}{a.status === 'acknowledged' && <span className="saved-label">Saved</span>}</span>
          <strong>{a.title}</strong><span className="notification-preview">{alertPreview(a)}</span>
        </span>
        <svg className={`notification-chevron ${expanded ? 'is-open' : ''}`} width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true"><path d="m5 7 5 5 5-5" /></svg>
      </button>
      {a.status === 'new' && <button className="ghost notification-save" disabled={busy !== null} onClick={() => void act('save')}>{busy === 'save' ? 'Saving…' : 'Save for later'}</button>}
    </div>
    <div id={detailId} className="notification-detail" hidden={!expanded}>
      <p>{a.message}</p>
      {a.suggestion && <div className="notification-suggestion"><strong>Suggested next step{a.explanation_status === 'ai' ? ' · AI' : ''}</strong><p>{a.suggestion}</p></div>}
      {a.evidence.length > 0 && <details className="notification-sources"><summary>Sources ({a.evidence.length})</summary><ul>{a.evidence.map((ref, i) => <li key={`${ref.record_id}-${i}`}>
        {ref.document_id && onSource ? <button className="link" onClick={() => onSource(ref.document_id!)}>View {ref.kind === 'receipt_item' ? 'receipt' : 'invoice'}{ref.source_page ? ` · page ${ref.source_page}` : ''} →</button> : <span className="muted" title={ref.record_id}>{ref.kind === 'forecast_run' ? 'Forecast snapshot' : 'Source record'}</span>}
        {ref.quote && <blockquote>{ref.quote}</blockquote>}
      </li>)}</ul></details>}
      <div className="notification-detail-actions">
        {inbox ? <button className="primary" disabled={busy !== null} onClick={() => void act('resolve')}>{busy === 'resolve' ? 'Resolving…' : 'Resolve'}</button>
          : <button className="link" onClick={() => onOpenInbox?.(a.id)}>Open in Inbox →</button>}
        {inbox && a.status === 'acknowledged' && <small className="muted">Saved until you resolve it.</small>}
      </div>
    </div>
    {err && <div className="notification-error" role="alert">{err}</div>}
  </div>;
}

export default function AlertInbox({ feed, selection, onSource }: { feed: AlertFeed; selection: { id: string | null; token: number } | null; onSource: (id: string) => void }) {
  const [savedOnly, setSavedOnly] = useState(false);
  useEffect(() => { if (selection) setSavedOnly(false); }, [selection]);
  const all = feed.data?.items ?? [];
  const items = savedOnly ? all.filter((a) => a.status === 'acknowledged') : all;
  return <Card title="Notifications" className="notification-inbox" action={<div className="seg small">
    <button className={!savedOnly ? 'on' : ''} onClick={() => setSavedOnly(false)}>All alerts</button>
    <button className={savedOnly ? 'on' : ''} onClick={() => setSavedOnly(true)}>Saved{feed.data?.savedCount ? ` (${feed.data.savedCount})` : ''}</button>
  </div>}>
    {feed.error ? <ErrorBox>Couldn't refresh alerts: {errorText(feed.error)}</ErrorBox> : null}
    <div className="notification-inbox-list" aria-busy={feed.loading}>
      {feed.loading ? <Empty>Loading notifications…</Empty> : items.length === 0 ? <Empty>{savedOnly ? 'No saved alerts.' : 'No open alerts.'}</Empty> : items.map((a) => <AlertItem key={a.id} a={a} inbox onChanged={feed.update} onSource={onSource} reveal={selection?.id === a.id ? selection.token : 0} />)}
    </div>
  </Card>;
}
