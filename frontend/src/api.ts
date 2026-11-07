import { consumeNDJSON, type StreamEvent } from './ndjson.mjs';

export type Source = { id: string; title: string; text: string };
export type RunInput = { task: string; sources: Source[]; image?: string };
export type Analysis = {
  summary: string;
  findings: { title: string; detail: string; evidence: { source_id: string; quote: string }[] }[];
  next_steps: string[];
  unknowns: string[];
};
export type RunOutput = {
  result: Analysis;
  meta: { mode: string; model: string; elapsed_ms: number; usage: Record<string, unknown>; warnings: string[] };
};
export type Health = { status: string; mode: string; model: string; configured: boolean };

async function checkedFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}). Check input limits and server status.`);
  }
  return response;
}

export async function health(): Promise<Health> {
  return (await checkedFetch('/api/health')).json();
}

export async function run(input: RunInput, signal: AbortSignal): Promise<RunOutput> {
  return (await checkedFetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal })).json();
}

export async function stream(input: RunInput, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  const response = await checkedFetch('/api/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal });
  if (!response.body) throw new Error('This browser did not provide a response stream.');
  await consumeNDJSON(response.body, onEvent);
}
