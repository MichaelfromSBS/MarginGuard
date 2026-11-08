import { useEffect, useRef, useState } from 'react';
import type {
  Alert, CatalogResponse, ChatMessage, ChatResponse, DashboardResponse, Document, DocumentDetail, DocumentType,
  ForecastResponse, ForecastRequest, IngredientPrice, Invoice, Page, Restaurant, CapabilitiesResponse, WorkerStatus,
  PricingScenarioRequest, PricingScenarioResponse,
} from '../marginguard-api';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<{ data: T; res: Response }> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let code = `http_${res.status}`;
    let message = res.statusText || 'Request failed';
    try {
      const body = await res.json();
      if (body?.error) { code = body.error.code; message = body.error.message; }
      else if (body?.detail) message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, code, message);
  }
  return { data: (await res.json()) as T, res };
}
const get = <T,>(path: string) => request<T>(path).then((r) => r.data);
const qs = (params: Record<string, string | number | undefined>) =>
  Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');

export const api = {
  health: () => get<{ status: string; mode: 'mock' | 'openrouter'; demo_as_of?: string | null }>('/api/health'),
  restaurant: () => get<Restaurant>('/api/restaurant'),
  catalog: () => get<CatalogResponse>('/api/catalog'),
  capabilities: () => get<CapabilitiesResponse>('/api/capabilities'),
  worker: () => get<WorkerStatus>('/api/worker'),
  prices: (ingredientId: string) => get<Page<IngredientPrice>>(`/api/ingredients/${encodeURIComponent(ingredientId)}/prices?limit=100`),
  documents: (p: { document_type?: DocumentType; limit?: number; offset?: number }) => get<Page<Document>>(`/api/documents?${qs(p)}`),
  document: (id: string) => get<DocumentDetail>(`/api/documents/${id}`),
  sourceUrl: (id: string) => `/api/documents/${id}/source`,
  upload: async (type: DocumentType, file: File) => {
    const form = new FormData();
    form.append('document_type', type);
    form.append('file', file, file.name);
    const { data, res } = await request<Document>('/api/documents', { method: 'POST', body: form });
    return { doc: data, duplicate: res.headers.get('X-MarginGuard-Duplicate') === 'true' };
  },
  process: (id: string) => request<Document>(`/api/documents/${id}/process`, { method: 'POST' }).then((r) => r.data),
  invoices: () => get<Page<Invoice>>('/api/invoices?limit=100'),
  alerts: (status?: Alert['status']) => get<Page<Alert>>(`/api/alerts?${qs({ status, limit: 100 })}`),
  // The existing persisted "acknowledged" state represents Save for later in the UI.
  saveAlertForLater: (id: string) => request<Alert>(`/api/alerts/${id}/acknowledge`, { method: 'POST' }).then((r) => r.data),
  resolve: (id: string) => request<Alert>(`/api/alerts/${id}/resolve`, { method: 'POST' }).then((r) => r.data),
  dashboard: () => get<DashboardResponse>('/api/dashboard'),
  forecasts: () => get<Page<ForecastResponse>>('/api/forecasts?limit=5'),
  recalculate: (policy: ForecastRequest = {}) => request<ForecastResponse>('/api/forecasts/recalculate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(policy),
  }).then((r) => r.data),
  pricingScenario: (id: string, policy: PricingScenarioRequest, signal?: AbortSignal) => request<PricingScenarioResponse>(`/api/forecasts/${encodeURIComponent(id)}/pricing-scenario`, {
    signal, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(policy),
  }).then((r) => r.data),
  chat: (question: string, history: ChatMessage[] = []) => request<ChatResponse>('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, history }),
  }).then((r) => r.data),
};

/** 501 = the backend has reserved this feature for a later checkpoint. */
export const isNotYet = (e: unknown) => e instanceof ApiError && e.status === 501;
export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Recent uploaded documents plus imported invoices; imported history receipts only on request. */
export async function loadDocuments(includeHistoryReceipts: boolean): Promise<Document[]> {
  const [invoices, first] = await Promise.all([
    api.documents({ document_type: 'invoice', limit: 100 }),
    api.documents({ document_type: 'receipt', limit: 1 }),
  ]);
  const receipts = await api.documents({ document_type: 'receipt', limit: 100, offset: Math.max(0, first.total - 100) });
  let all = [...invoices.items, ...receipts.items];
  if (!includeHistoryReceipts) all = all.filter((d) => d.media_type !== 'text/plain');
  return all.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/** Fetch now and every `ms` milliseconds (0 = once). */
export function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  const revision = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    let inFlight = false;
    setData(null);
    setError(null);
    const run = async () => {
      if (inFlight) return;
      inFlight = true;
      const startedAtRevision = revision.current;
      try {
        const d = await fnRef.current();
        if (alive && startedAtRevision === revision.current) { setData(d); setError(null); }
      } catch (e) {
        if (alive && startedAtRevision === revision.current) setError(e);
      } finally { inFlight = false; }
    };
    run();
    const timer = ms ? window.setInterval(run, ms) : undefined;
    return () => { alive = false; if (timer) window.clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, ms]);
  return { data, error, loading: data === null && error === null, refresh: () => setTick((t) => t + 1),
    update: (value: T) => { revision.current++; setData(value); setError(null); } };
}
