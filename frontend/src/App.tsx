import { useEffect, useRef, useState } from 'react';
import { health, run, stream, type Health, type RunOutput, type Source } from './api';

const sampleSources: Source[] = [
  { id: 'brief', title: 'Sample event brief (fictional)', text: 'The demo starts Saturday at 4:00 PM. Each team gets three minutes to present. A working prototype is required.' },
  { id: 'update', title: 'Sample team message (fictional)', text: 'I thought our demo was at 4:30 PM on Saturday. I prepared a five-minute presentation. The prototype is ready.' },
];
const sampleTask = 'Compare these fictional notes. Identify conflicting assumptions, cite the exact source passages, and suggest what the team should clarify. Do not decide which source is authoritative.';

export default function App() {
  const [status, setStatus] = useState<Health | null>(null);
  const [task, setTask] = useState(sampleTask);
  const [sources, setSources] = useState<Source[]>(sampleSources);
  const [image, setImage] = useState<string>();
  const [imageName, setImageName] = useState('');
  const [mode, setMode] = useState<'structured' | 'text'>('structured');
  const [result, setResult] = useState<RunOutput | null>(null);
  const [resultSources, setResultSources] = useState<Source[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const abort = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    health().then(setStatus).catch(() => setError('Backend unavailable. Start the app with npm run dev, then refresh.'));
    return () => abort.current?.abort();
  }, []);

  function updateSource(index: number, patch: Partial<Source>) {
    setSources(old => old.map((source, i) => i === index ? { ...source, ...patch } : source));
  }

  async function attachImage(file?: File) {
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 3 * 1024 * 1024) {
      setError('Choose a PNG, JPEG, or WebP image up to 3 MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => { setImage(String(reader.result)); setImageName(file.name); setError(''); };
    reader.onerror = () => setError('Could not read that image.');
    reader.readAsDataURL(file);
  }

  async function submit() {
    if (!task.trim() || busy) return;
    if (sources.some(source => !source.title.trim() || !source.text.trim())) {
      setError('Fill in each source, or remove empty sources before running.');
      return;
    }
    setBusy(true); setError(''); setNotice(''); setResult(null); setText('');
    const controller = new AbortController();
    abort.current = controller;
    try {
      const input = { task, sources, ...(image ? { image } : {}) };
      if (mode === 'structured') {
        setResultSources(sources);
        setResult(await run(input, controller.signal));
      } else {
        await stream(input, controller.signal, event => {
          if (event.type === 'token') setText(old => old + (event.text ?? ''));
        });
      }
    } catch (e) {
      if (controller.signal.aborted) setNotice('Stopped locally. An upstream request may continue briefly.');
      else setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      abort.current = null; setBusy(false);
    }
  }

  function download() {
    const content = result ? JSON.stringify(result, null, 2) : text;
    const url = URL.createObjectURL(new Blob([content], { type: result ? 'application/json' : 'text/plain' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = result ? 'nova-result.json' : 'nova-result.txt'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <main>
    <header>
      <a className="brand" href="/" aria-label="NOVA AI Workbench home"><span className="brand-icon">✳</span> NOVA <span className="brand-sub">/ AI WORKBENCH</span></a>
      <span className={`status ${status?.configured ? 'online' : ''}`}><i />{status ? `${status.mode === 'mock' ? 'MOCK · no model calls' : status.configured ? 'OpenRouter · configured' : 'OpenRouter · setup needed'}` : 'Connecting…'}</span>
    </header>

    <section className="intro">
      <div className="eyebrow">YOUR IDEA STARTS HERE</div>
      <h1>Less setup.<br /><span>More making.</span></h1>
      <p>A small workspace for testing an AI workflow.<br />Bring a task, add context, and shape what comes back.</p>
      <div className="pipeline"><span>01 / INPUT</span><b>→</b><span>02 / MODEL</span><b>→</b><span>03 / RESULT</span></div>
    </section>

    {status?.mode === 'mock' && <div className="banner"><strong>You're in fixture mode.</strong> Run either workflow to test the plumbing. Results are sample fixtures, not AI answers.</div>}
    <div className="workspace">
      <section className="panel input-panel">
        <div className="panel-heading"><div><span className="eyebrow">01 / INPUT</span><h2>Set the task</h2></div><button className="text-button" disabled={busy} onClick={() => { setTask(sampleTask); setSources(sampleSources); setImage(undefined); setImageName(''); setResult(null); setText(''); setError(''); setNotice(''); }}>Load sample ↗</button></div>
        <fieldset disabled={busy}>
          <label htmlFor="task">What should the model do?</label>
          <textarea id="task" className="task" maxLength={4000} value={task} onChange={event => setTask(event.target.value)} />
          <div className="source-heading"><label>Source material <span className="optional">OPTIONAL</span></label><span>{sources.length} / 8</span></div>
          <p className="hint">Paste excerpts or notes. Structured results can cite these sources.</p>
          <div className="source-list">{sources.map((source, index) => <div className="source" key={source.id}>
            <div className="source-top"><span className="source-number">{String(index + 1).padStart(2, '0')}</span><input aria-label={`Source ${index + 1} title`} maxLength={160} value={source.title} onChange={event => updateSource(index, { title: event.target.value })} /><button className="remove" aria-label={`Remove source ${index + 1}`} onClick={() => setSources(old => old.filter(item => item.id !== source.id))}>×</button></div>
            <textarea aria-label={`Source ${index + 1} text`} maxLength={32000} value={source.text} onChange={event => updateSource(index, { text: event.target.value })} placeholder="Paste source text…" />
          </div>)}</div>
          <button className="add-source" disabled={sources.length >= 8} onClick={() => setSources(old => [...old, { id: `source-${crypto.randomUUID()}`, title: '', text: '' }])}>+ Add a source</button>
          <input ref={fileRef} type="file" hidden accept="image/png,image/jpeg,image/webp" onChange={event => { void attachImage(event.target.files?.[0]); event.target.value = ''; }} />
          <div className="image-row"><button className="text-button" onClick={() => fileRef.current?.click()}>+ {image ? 'Replace image' : 'Attach an image'}</button><span className="hint">PNG, JPG, WebP · up to 3 MB</span></div>
          {image && <div className="image-preview"><img src={image} alt="Attached context" /><span>{imageName}</span><button className="remove" aria-label="Remove image" onClick={() => { setImage(undefined); setImageName(''); }}>×</button></div>}
          <label className="output-label">Output format</label>
          <div className="mode-switch"><button aria-pressed={mode === 'structured'} className={mode === 'structured' ? 'selected' : ''} onClick={() => setMode('structured')}>Structured cards</button><button aria-pressed={mode === 'text'} className={mode === 'text' ? 'selected' : ''} onClick={() => setMode('text')}>Streaming text</button></div>
        </fieldset>
        <div className="run-row"><button className="run-button" disabled={busy || !task.trim() || !status?.configured} onClick={() => void submit()}>{busy ? <><span className="spinner" /> Working…</> : <>Run workflow <span>↗</span></>}</button>{busy && <button className="text-button" onClick={() => abort.current?.abort()}>Stop</button>}</div>
        <p className="privacy">Live mode sends your inputs to OpenRouter and its model provider. This starter does not save inputs.</p>
      </section>

      <section className="panel output-panel" aria-busy={busy}>
        <div className="panel-heading"><div><span className="eyebrow">03 / OUTPUT</span><h2>See what takes shape</h2></div>{(result || text) && <button className="text-button" onClick={download}>Export ↓</button>}</div>
        <div aria-live="polite">{error && <div className="error" role="alert">{error}</div>}{notice && <div className="banner">{notice}</div>}</div>
        {!result && !text && <div className="empty-state"><div className={`orbit ${busy ? 'working' : ''}`}><span>✳</span></div><h3>{busy ? 'Making connections…' : 'A place for your next idea.'}</h3><p>{busy ? 'The workflow is running. Your result will appear here.' : 'Run the sample to check the connection, then make this workflow your own.'}</p><div className="empty-tags"><span>Source context</span><span>Image input</span><span>Typed output</span></div></div>}
        {text && <><div className="result-label">{status?.mode === 'mock' ? 'MOCK STREAM' : 'TEXT RESPONSE · citations not checked'}</div><pre className="stream-text">{text}</pre></>}
        {result && <div className="results">
          <div className="result-label">{result.meta.mode === 'mock' ? 'MOCK FIXTURE' : result.meta.model} <span>{(result.meta.elapsed_ms / 1000).toFixed(2)}s</span></div>
          <p className="summary">{result.result.summary}</p>
          {result.meta.warnings.map((warning, index) => <div className="warning" key={index}>{warning}</div>)}
          <h3>Findings <span className="count">{result.result.findings.length}</span></h3>
          {result.result.findings.map((finding, index) => <article className="finding" key={index}><span className="finding-index">{String(index + 1).padStart(2, '0')}</span><div><h4>{finding.title}</h4><p>{finding.detail}</p>{finding.evidence.map((evidence, i) => <blockquote key={i}>“{evidence.quote}”<cite>{resultSources.find(source => source.id === evidence.source_id)?.title ?? evidence.source_id}</cite></blockquote>)}</div></article>)}
          <div className="next"><h3>Next steps</h3><ol>{result.result.next_steps.map((step, i) => <li key={i}>{step}</li>)}</ol></div>
          {result.result.unknowns.length > 0 && <div className="unknowns"><h3>Still unknown</h3><ul>{result.result.unknowns.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
          <p className="hint">Quote matching checks that text appears in a source. It does not establish that a conclusion is correct.</p>
          {Object.keys(result.meta.usage).length > 0 && <details><summary>Model usage</summary><pre>{JSON.stringify(result.meta.usage, null, 2)}</pre></details>}
        </div>}
      </section>
    </div>
    <footer><span>NOVA 2026 · STARTER WORKSPACE</span><span>One focused workflow. Something worth showing.</span></footer>
  </main>;
}
