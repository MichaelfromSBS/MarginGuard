import { useEffect, useRef, useState } from 'react';
import Ask from './Ask';

export default function FloatingChat({ visible, onSource }: { visible: boolean; onSource: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open) panel.current?.querySelector('input')?.focus({ preventScroll: true });
    else if (wasOpen.current) launcher.current?.focus({ preventScroll: true });
    wasOpen.current = open;
  }, [open]);

  useEffect(() => {
    if (!visible || !open) return;
    const chat = panel.current?.querySelector('.chat');
    if (chat) chat.scrollTop = chat.scrollHeight;
  }, [open, visible]);

  return <aside className="floating-chat" aria-label="MarginGuard assistant" hidden={!visible}>
    <div ref={panel} id="floating-chat-panel" className={`floating-chat-panel ${open ? 'is-open' : ''}`}
      aria-hidden={!open} inert={!open || !visible}
      onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); setOpen(false); } }}>
      <Ask onSource={onSource} onMinimize={() => setOpen(false)} />
    </div>
    <button ref={launcher} className="chat-launcher" hidden={open} aria-expanded={open}
      aria-controls="floating-chat-panel" onClick={() => setOpen(true)}>
      <span className="chat-launcher-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l-3 3V11.5a9 9 0 1 1 18 0Z" /><path d="M7 10h8M7 14h5" /></svg></span>
      <span><b>Ask MarginGuard</b><small>Make sense of your numbers</small></span>
      <svg className="chat-launcher-arrow" viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m6 12 4-4 4 4" /></svg>
    </button>
  </aside>;
}
