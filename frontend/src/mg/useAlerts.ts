import { useCallback, useEffect, useRef, useState } from 'react';
import type { Alert } from '../marginguard-api';
import { api } from './client';

export interface AlertList { items: Alert[]; newCount: number; savedCount: number }

/** Apply a successful action without clearing either view or waiting for the next poll. */
export function updateAlertList(list: AlertList, updated: Alert): AlertList {
  const previous = list.items.find((a) => a.id === updated.id);
  const items = list.items.filter((a) => a.id !== updated.id);
  if (updated.status !== 'resolved') items.push(updated);
  items.sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id));
  return {
    items,
    newCount: Math.max(0, list.newCount - Number(previous?.status === 'new') + Number(updated.status === 'new')),
    savedCount: Math.max(0, list.savedCount - Number(previous?.status === 'acknowledged') + Number(updated.status === 'acknowledged')),
  };
}

/** One shared feed for Overview, Inbox, the bell and toast notifications. */
export default function useAlerts() {
  const [data, setData] = useState<AlertList | null>(null);
  const [error, setError] = useState<unknown>(null);
  const revision = useRef(0);
  useEffect(() => {
    let alive = true, inFlight = false;
    const run = async () => {
      if (inFlight) return;
      inFlight = true;
      const startedAt = revision.current;
      try {
        const [fresh, saved] = await Promise.all([api.alerts('new'), api.alerts('acknowledged')]);
        if (alive && startedAt === revision.current) {
          setData({ items: [...fresh.items, ...saved.items].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id)), newCount: fresh.total, savedCount: saved.total });
          setError(null);
        }
      } catch (e) { if (alive && startedAt === revision.current) setError(e); }
      finally { inFlight = false; }
    };
    void run();
    const timer = window.setInterval(run, 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);
  const update = useCallback((alert: Alert) => {
    revision.current++;
    setData((current) => current ? updateAlertList(current, alert) : current);
  }, []);
  return { data, error, loading: data === null && error === null, update };
}

export type AlertFeed = ReturnType<typeof useAlerts>;
