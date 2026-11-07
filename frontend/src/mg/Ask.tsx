import { useEffect, useRef, useState } from 'react';
import type { ChatResponse } from '../marginguard-api';
import { api, errorText } from './client';
import { MetricCard } from './Metrics';
import { Card } from './ui';

type Msg = { role: 'user' | 'assistant'; text: string; data?: ChatResponse; notice?: boolean };
const SUGGESTED = [
  'Why did next month’s ingredient cost increase?',
  'What does the Classic Burger cost to make now?',
  'How has the beef price changed?',
  'What were sales in the last 7 days?',
  'Which alerts need my attention?',
];

export default function Ask({ onSource, onMinimize }: { onSource: (id: string) => void; onMinimize?: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  // Scroll only inside the chat box, so opening the Overview never jumps the page.
  useEffect(() => { if (box.current && msgs.length) box.current.scrollTop = box.current.scrollHeight; }, [msgs, busy]);

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setMsgs((m) => [...m, { role: 'user', text }]); setQ(''); setBusy(true);
    try {
      const history = msgs.filter((m) => !m.notice).slice(-6).map((m) => ({ role: m.role, content: m.text.slice(0, 2000) }));
      const data = await api.chat(text, history);
      setMsgs((m) => [...m, { role: 'assistant', text: data.answer, data }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', notice: true, text: errorText(e) }]);
    } finally { setBusy(false); }
  };

  return (
    <Card title="Ask MarginGuard" action={<div className="chat-head-actions"><small className="muted">figures from your records · read-only</small>
      {onMinimize && <button className="chat-minimize" aria-label="Minimize chat" onClick={onMinimize}><svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 10h12" /></svg></button>}
    </div>} className="ask">
      <div className="chat" ref={box}>
        {msgs.length === 0 && (
          <div className="chat-empty">
            <p>Ask about sales, costs, forecasts or alerts. You can also ask me to explain an answer.</p>
            <div className="chips">{SUGGESTED.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role} ${m.notice || (m.data && m.data.status !== 'answered') ? 'notice' : ''}`}>
            <p style={{ whiteSpace: 'pre-line' }}>{m.text}</p>
            {m.data && <small className="muted">{m.data.answer_method === 'ai_explanation' ? 'AI explanation · no new business figures' : `${m.data.status === 'answered' ? 'Database answer' : m.data.status.replace('_', ' ')} · ledger v${m.data.source_data_version} · checked ${new Date(m.data.as_of).toLocaleString()}`}</small>}
            {m.data && m.data.metrics.length > 0 && <div className="metrics small">{m.data.metrics.map((x) => <MetricCard key={x.id} m={x} />)}</div>}
            {m.data && m.data.evidence.length > 0 && (
              <details className="sources"><summary>Sources ({m.data.evidence.length})</summary>{m.data.evidence.map((e, j) => <div key={j}>
                {e.document_id ? <button className="chip" onClick={() => onSource(e.document_id!)}>{e.kind.replaceAll('_', ' ')} · {e.record_id}{e.source_page ? ` · p${e.source_page}` : ''}</button>
                  : <span className="chip static">{e.kind.replaceAll('_', ' ')} · {e.record_id}</span>}
                {e.quote && <small>{e.quote}</small>}
              </div>)}</details>
            )}
            {m.data && m.data.tools.length > 0 && <details><summary>Queries used</summary>{m.data.tools.map((t, j) => <div key={j}><small>{t.name.replaceAll('_', ' ')} · {t.status}</small><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(t.arguments)}</pre></div>)}</details>}
            {m.data && m.data.limitations.length > 0 && <small className="muted">{m.data.limitations.join(' ')}</small>}
          </div>
        ))}
        {busy && <div className="bubble assistant"><p className="muted"><i className="pulse" /> Looking it up…</p></div>}
      </div>
      <form className="ask-row" onSubmit={(e) => { e.preventDefault(); send(q); }}>
        <input aria-label="Question about restaurant records" maxLength={4000} value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. What does the Classic Burger cost now?" />
        <button className="primary" disabled={!q.trim() || busy}>Ask</button>
      </form>
    </Card>
  );
}
