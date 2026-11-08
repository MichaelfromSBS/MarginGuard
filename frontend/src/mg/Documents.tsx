import { useEffect, useRef, useState } from 'react';
import type { DocumentDetail, DocumentType, InvoiceExtraction, ReceiptExtraction } from '../marginguard-api';
import { api, errorText, loadDocuments, usePoll } from './client';
import { dateTime, label, money, qty, timeAgo, subtractDecimal } from './format';
import { Card, Empty, ErrorBox, Pill, StatusBadge } from './ui';
import AlertInbox from './Alerts';
import type { AlertFeed } from './useAlerts';

export default function Documents({ selectedId, onSelect, alerts, alertSelection }: { selectedId: string | null; onSelect: (id: string | null) => void; alerts: AlertFeed; alertSelection: { id: string | null; token: number } | null }) {
  const [showHistory, setShowHistory] = useState(false);
  const [filter, setFilter] = useState<'all' | 'attention'>('all');
  const list = usePoll(() => loadDocuments(showHistory), 3000, [showHistory]);
  const docs = (list.data ?? []).filter((d) => filter === 'all' || d.status === 'needs_review' || d.status === 'failed');
  const attention = (list.data ?? []).filter((d) => d.status === 'needs_review' || d.status === 'failed').length;
  const reviewPanel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!selectedId) return;
    reviewPanel.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    reviewPanel.current?.focus({ preventScroll: true });
  }, [selectedId]);

  return (
    <div className="stack">
    <AlertInbox feed={alerts} selection={alertSelection} onSource={onSelect} />
    <div className="docs-layout">
      <div className="stack">
        <Upload onUploaded={(id) => { onSelect(id); list.refresh(); }} />
        <Card
          title="Documents"
          action={<div className="seg small">
            <button className={filter === 'all' ? 'on' : ''} onClick={() => setFilter('all')}>All</button>
            <button className={filter === 'attention' ? 'on' : ''} onClick={() => setFilter('attention')}>Needs attention{attention ? ` (${attention})` : ''}</button>
          </div>}
        >
          {list.error ? <ErrorBox>Couldn't load documents: {errorText(list.error)}</ErrorBox> : null}
          <div className="document-results" aria-busy={list.loading}>
          {list.loading && <div className="document-placeholder" role="status" aria-label="Loading documents">
            <span className="muted">Loading documents…</span>
            {Array.from({ length: 6 }, (_, i) => <div className="document-skeleton" key={i} aria-hidden="true"><i /><span><b /><small /></span></div>)}
          </div>}
          {list.data && docs.length === 0 && <Empty>{filter === 'attention' ? 'Nothing needs attention.' : 'No documents yet. Upload one above.'}</Empty>}
          <ul className="doclist">
            {docs.map((d) => (
              <li key={d.id}>
                <button className={`docrow ${selectedId === d.id ? 'sel' : ''}`} onClick={() => onSelect(d.id)}>
                  <span className={`doctype ${d.type}`}>{d.type === 'invoice' ? 'INV' : 'RCPT'}</span>
                  <span className="docname"><b>{d.filename}</b><small>{timeAgo(d.created_at)}{d.media_type === 'text/plain' ? ' · imported history' : ''}</small></span>
                  <StatusBadge status={d.status} />
                </button>
              </li>
            ))}
          </ul>
          </div>
          <label className="check"><input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} /> Show latest imported history receipts</label>
        </Card>
      </div>
      <div ref={reviewPanel} tabIndex={-1} className="document-review">{selectedId ? <Detail key={selectedId} id={selectedId} /> : <Card><Empty>Select a document to review.</Empty></Card>}</div>
    </div>
    </div>
  );
}

function Upload({ onUploaded }: { onUploaded: (id: string) => void }) {
  const [type, setType] = useState<DocumentType>('invoice');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f); setMsg(null);
    if (/receipt|rcpt|tb-/i.test(f.name)) setType('receipt');
    else if (/invoice|inv|rf-|apc-/i.test(f.name)) setType('invoice');
  };
  const submit = async () => {
    if (!file) return;
    setBusy(true); setMsg(null);
    try {
      const { doc, duplicate } = await api.upload(type, file);
      setMsg(duplicate
        ? { tone: 'warn', text: 'Already uploaded · no duplicate counted.' }
        : { tone: 'ok', text: 'Uploaded. The AI is reading it now.' });
      setFile(null); if (input.current) input.current.value = '';
      onUploaded(doc.id);
    } catch (e) {
      setMsg({ tone: 'bad', text: errorText(e) });
    } finally { setBusy(false); }
  };

  return (
    <Card title="Add a document">
      <div className="seg">
        <button className={type === 'invoice' ? 'on' : ''} onClick={() => setType('invoice')}>Supplier invoice</button>
        <button className={type === 'receipt' ? 'on' : ''} onClick={() => setType('receipt')}>Customer receipt</button>
      </div>
      <div
        className={`drop ${drag ? 'drag' : ''}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
      >
        <input ref={input} type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" hidden onChange={(e) => pick(e.target.files?.[0])} />
        {file ? <><b>{file.name}</b><small>{(file.size / 1024).toFixed(0)} KB · click to change</small></>
          : <><b>Drop a PDF or photo here</b><small>or click to browse · PDF, PNG, JPG</small></>}
      </div>
      <button className="primary wide" disabled={!file || busy} onClick={submit}>{busy ? 'Uploading…' : `Upload ${type}`}</button>
      {msg && <p className={`note ${msg.tone}`}>{msg.text}</p>}
    </Card>
  );
}

function Detail({ id }: { id: string }) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState('');
  const [view, setView] = useState<'fields' | 'source'>('fields');
  const d = usePoll(() => api.document(id), 2500, [id]);
  useEffect(() => { setView('fields'); }, [id]);
  const doc = d.data;
  if (d.error) return <Card><ErrorBox>{errorText(d.error)}</ErrorBox></Card>;
  if (!doc) return <Card><Empty>Loading…</Empty></Card>;
  const busy = doc.status === 'detected' || doc.status === 'processing';
  const method = doc.extraction_method === 'openrouter' ? 'AI extraction'
    : doc.extraction_method === 'fixture_history' ? 'Imported history (prepared data)'
    : doc.extraction_method === 'fixture_expected' ? 'Prepared fixture (no AI call)' : doc.extraction_method ?? '—';

  const retry = async () => {
    setRetrying(true); setRetryError('');
    try { await api.process(doc.id); d.refresh(); } catch (e) { setRetryError(errorText(e)); } finally { setRetrying(false); }
  };

  return (
    <Card
      className="detail"
      title={<span className="detail-title">{doc.filename}</span>}
      action={<StatusBadge status={doc.status} />}
    >
      <div className="meta">
        <span>{label(doc.type)}</span><span>{method}</span><span>Uploaded {dateTime(doc.created_at)}</span>
        {doc.evidence_mode === 'visual' && <span>Read from image</span>}
      </div>
      {retryError && <ErrorBox>{retryError}</ErrorBox>}
      {busy && <div className="reading"><i className="pulse" /> The AI is reading this document…</div>}
      {doc.status === 'failed' && (
        <ErrorBox>
          <b>{label(doc.error_code)}</b>: {doc.error_message}
          <div><button className="ghost" onClick={retry} disabled={retrying}>{retrying ? 'Retrying…' : 'Retry'}</button></div>
        </ErrorBox>
      )}
      {doc.validation_issues.length > 0 && (
        <div className="issues">
          <b>{doc.status === 'needs_review' ? 'Held for review: not added to the books' : 'Validation notes'}</b>
          <ul>{doc.validation_issues.map((v, i) => <li key={i}>{v.message}{v.item_index !== null ? ` (line ${v.item_index + 1})` : ''}</li>)}</ul>
        </div>
      )}
      <div className="seg small">
        <button className={view === 'fields' ? 'on' : ''} onClick={() => setView('fields')}>Extracted data</button>
        <button className={view === 'source' ? 'on' : ''} onClick={() => setView('source')}>Original document</button>
      </div>
      {view === 'fields' ? <Fields doc={doc} /> : <Source doc={doc} />}
    </Card>
  );
}

function Fields({ doc }: { doc: DocumentDetail }) {
  const x = doc.extraction;
  if (!x) return <Empty>No extracted data yet.</Empty>;
  if (doc.type === 'invoice') {
    const inv = x as InvoiceExtraction;
    return (
      <>
        <dl className="kv">
          <div><dt>Supplier</dt><dd>{inv.vendor_name}</dd></div>
          <div><dt>Invoice #</dt><dd>{inv.invoice_number}</dd></div>
          <div><dt>Date</dt><dd>{inv.invoice_date}</dd></div>
          <div><dt>Total</dt><dd className="strong">{money(inv.total)}</dd></div>
        </dl>
        <table className="tbl">
          <thead><tr><th>Item</th><th>Matched to</th><th className="r">Qty</th><th>Pack</th><th className="r">Unit price</th><th className="r">Line total</th></tr></thead>
          <tbody>{inv.items.map((it, i) => (
            <tr key={i} title={`Source: "${it.source_text}" (page ${it.source_page})`}>
              <td>{it.description}</td>
              <td>{it.ingredient_id ? label(it.ingredient_id) : <Pill tone="warn">Unknown</Pill>}</td>
              <td className="r">{qty(it.quantity)} {it.purchase_unit}</td>
              <td>{it.pack_size ? `${qty(it.pack_size)} ${it.pack_unit}` : it.purchase_unit === 'case' ? <Pill tone="warn">Missing</Pill> : '—'}</td>
              <td className="r">{money(it.unit_price)}</td>
              <td className="r">{money(it.line_total)}</td>
            </tr>
          ))}</tbody>
          <tfoot>
            <tr><td colSpan={5} className="r">Subtotal</td><td className="r">{money(inv.subtotal)}</td></tr>
            {inv.tax !== '0.00' && <tr><td colSpan={5} className="r">Tax</td><td className="r">{money(inv.tax)}</td></tr>}
            {inv.freight !== '0.00' && <tr><td colSpan={5} className="r">Freight</td><td className="r">{money(inv.freight)}</td></tr>}
            <tr className="strong"><td colSpan={5} className="r">Total</td><td className="r">{money(inv.total)}</td></tr>
          </tfoot>
        </table>
        <p className="hint">Hover a line for its source.</p>
      </>
    );
  }
  const r = x as ReceiptExtraction;
  return (
    <>
      <dl className="kv">
        <div><dt>Receipt #</dt><dd>{r.receipt_number}</dd></div>
        <div><dt>Sold</dt><dd>{dateTime(r.sold_at)}</dd></div>
        <div><dt>Channel</dt><dd>{r.channel_id ? label(r.channel_id) : <Pill tone="warn">Unknown</Pill>}</dd></div>
        <div><dt>Net item revenue</dt><dd className="strong">{money(subtractDecimal(r.subtotal, r.discount))}</dd></div>
      </dl>
      <table className="tbl">
        <thead><tr><th>Item</th><th>Matched to</th><th className="r">Qty</th><th className="r">Price</th><th className="r">Amount</th></tr></thead>
        <tbody>{r.items.map((it, i) => (
          <tr key={i} title={`Source: "${it.source_text}"`}>
            <td>{it.description}</td>
            <td>{it.dish_id ? label(it.dish_id) : <Pill tone="warn">Unknown dish</Pill>}</td>
            <td className="r">{qty(it.quantity)}</td><td className="r">{money(it.unit_price)}</td><td className="r">{money(it.net_amount)}</td>
          </tr>
        ))}</tbody>
        <tfoot>
          <tr><td colSpan={4} className="r">Subtotal</td><td className="r">{money(r.subtotal)}</td></tr>
          {r.discount !== '0.00' && <tr><td colSpan={4} className="r">Discount</td><td className="r">-{money(r.discount)}</td></tr>}
          <tr><td colSpan={4} className="r">Tax</td><td className="r">{money(r.tax)}</td></tr>
          {r.tip !== '0.00' && <tr><td colSpan={4} className="r">Tip</td><td className="r">{money(r.tip)}</td></tr>}
          <tr className="strong"><td colSpan={4} className="r">Total charged</td><td className="r">{money(r.total)}</td></tr>
        </tfoot>
      </table>
      <p className="hint">Net sales exclude tax and tips.</p>
    </>
  );
}

function Source({ doc }: { doc: DocumentDetail }) {
  if (doc.media_type === 'text/plain' || doc.extraction_method === 'fixture_history') {
    return doc.source_text ? <pre className="srctext">{doc.source_text}</pre> : <Empty>No original file stored.</Empty>;
  }
  const url = api.sourceUrl(doc.id);
  return doc.media_type.startsWith('image/')
    ? <img className="srcimg" src={url} alt={doc.filename} />
    : <iframe className="srcpdf" src={url} title={doc.filename} />;
}
