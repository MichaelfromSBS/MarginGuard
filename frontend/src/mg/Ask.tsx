import { useEffect, useRef, useState } from 'react';
import type { ChatResponse } from '../marginguard-api';
import { api, errorText, isNotYet } from './client';
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

export default function Ask() {
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
      const data = await api.chat(text);
      setMsgs((m) => [...m, { role: 'assistant', text: data.answer, data }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', notice: true, text: isNotYet(e)
        ? 'Chat isn’t switched on yet. It arrives with checkpoint 5 and will answer from the restaurant’s own records, with sources.'
        : `Something went wrong: ${errorText(e)}` }]);
    } finally { setBusy(false); }
  };

  return (
    <Card title="Ask MarginGuard" action={<small className="muted">answers come from your records, read-only</small>} className="ask">
      <div className="chat" ref={box}>
        {msgs.length === 0 && (
          <div className="chat-empty">
            <p>Ask about sales, costs, forecasts or alerts.</p>
            <div className="chips">{SUGGESTED.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role} ${m.notice ? 'notice' : ''}`}>
            <p>{m.text}</p>
            {m.data && m.data.metrics.length > 0 && <div className="metrics small">{m.data.metrics.map((x) => <MetricCard key={x.id} m={x} />)}</div>}
            {m.data && m.data.evidence.length > 0 && (
              <div className="sources">{m.data.evidence.map((e, j) => <span key={j} className="chip static" title={e.quote ?? ''}>{e.kind.replace('_', ' ')} · {e.record_id}</span>)}</div>
            )}
            {m.data && m.data.limitations.length > 0 && <small className="muted">{m.data.limitations.join(' ')}</small>}
          </div>
        ))}
        {busy && <div className="bubble assistant"><p className="muted"><i className="pulse" /> Looking it up…</p></div>}
      </div>
      <form className="ask-row" onSubmit={(e) => { e.preventDefault(); send(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Why did burger costs go up?" />
        <button className="primary" disabled={!q.trim() || busy}>Ask</button>
      </form>
    </Card>
  );
}
