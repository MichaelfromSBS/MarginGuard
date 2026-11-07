"""Persistent MarginGuard worker: python -m backend.worker [--once]."""
import argparse
import asyncio
from contextlib import suppress
from datetime import datetime
import json
import mimetypes
import sqlite3
from types import SimpleNamespace

import httpx

from backend.config import Settings
from backend.marginguard import analytics, detectors, forecasting, ingestion
from backend.marginguard.db import connect, initialize_database
from backend.marginguard.document_io import MAX_DOCUMENT_BYTES
from backend.marginguard.errors import DomainError
from backend.marginguard.extraction import extract_document
from backend.marginguard.jobs import later, exhaust_abandoned_jobs
from backend.marginguard.alert_explanations import enrich_alerts
from backend.marginguard.schemas import ForecastRequest


def set_state(conn, key, value):
    conn.execute("INSERT INTO worker_state(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def read_inbox_file(path):
    with path.open("rb") as source:
        return source.read(MAX_DOCUMENT_BYTES + 1)


def worker_status(conn, settings):
    row = conn.execute("SELECT * FROM worker_leases WHERE name='main'").fetchone()
    state = "not_started" if row is None else "stopped" if row["status"] == "stopped" else "running" if row["expires_at"] > ingestion.now() else "stale"
    count = lambda sql: conn.execute(sql).fetchone()[0]
    return {"status": state, "heartbeat_at": row["heartbeat_at"] if row else None, "error_code": row["error_code"] if row else None,
            "processing_mode": settings.processing_mode,
            "queued_documents": count("SELECT COUNT(*) FROM documents WHERE status='detected'"),
            "processing_documents": count("SELECT COUNT(*) FROM documents WHERE status='processing'"),
            "new_alerts": count("SELECT COUNT(*) FROM alerts WHERE status='new'"),
            "watched_file_errors": count("SELECT COUNT(*) FROM watched_files WHERE error_code IS NOT NULL")}


class Worker:
    def __init__(self, settings=None, *, client=None, extractor=None):
        self.settings = settings or Settings()
        self.owner = ingestion.identifier("worker")
        self.client = client
        self.own_client = client is None
        self.extractor = extractor or extract_document
        self.heartbeat_task = None
        self.lost_lease = False

    async def __aenter__(self):
        settings = self.settings
        initialize_database(settings.database_path)
        with connect(settings.database_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM worker_leases WHERE name='main'").fetchone()
            if row and row["status"] == "running" and row["expires_at"] > ingestion.now():
                raise DomainError("worker_already_running", "A worker already holds the database lease. Stop it or wait for its lease to expire.", 409)
            conn.execute("""INSERT INTO worker_leases(name,owner,expires_at,heartbeat_at,status,error_code) VALUES ('main',?,?,?,'running',NULL)
                ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at,heartbeat_at=excluded.heartbeat_at,status='running',error_code=NULL""",
                (self.owner, later(30), ingestion.now()))
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=httpx.Timeout(settings.ai_timeout_seconds, connect=10))
        self.app = SimpleNamespace(state=SimpleNamespace(settings=settings, database_path=settings.database_path, active_documents=set(),
                                    ai_lock=asyncio.Lock(), client=self.client, document_extractor=self.extractor))
        self.heartbeat_task = asyncio.create_task(self.heartbeat())
        return self

    async def heartbeat(self):
        while True:
            await asyncio.sleep(5)
            try:
                with connect(self.settings.database_path) as conn:
                    changed = conn.execute("UPDATE worker_leases SET expires_at=?,heartbeat_at=? WHERE name='main' AND owner=? AND status='running'",
                                           (later(30), ingestion.now(), self.owner)).rowcount
            except sqlite3.Error:
                continue
            if not changed:
                self.lost_lease = True
                return

    async def __aexit__(self, *args):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.heartbeat_task
        with connect(self.settings.database_path) as conn:
            conn.execute("UPDATE worker_leases SET status='stopped',expires_at=?,heartbeat_at=? WHERE name='main' AND owner=?", (ingestion.now(), ingestion.now(), self.owner))
        if self.own_client and self.client:
            await self.client.aclose()

    def check_lease(self, conn):
        row = conn.execute("SELECT owner,expires_at,status FROM worker_leases WHERE name='main'").fetchone()
        if self.lost_lease or not row or row["owner"] != self.owner or row["expires_at"] <= ingestion.now() or row["status"] != "running":
            raise DomainError("worker_lease_lost", "Worker lease expired or changed owner; stopping this worker.", 409)

    async def scan_inbox(self):
        settings = self.settings
        for kind, folder_name in [("invoice", "invoices"), ("receipt", "receipts")]:
            folder = settings.inbox_directory / folder_name
            if folder.is_symlink() or not folder.resolve().is_relative_to(settings.inbox_directory.resolve()):
                continue
            folder.mkdir(parents=True, exist_ok=True)
            for path in sorted(folder.iterdir())[:200]:
                if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                    continue
                try:
                    stat = path.stat()
                    resolved = str(path.resolve())
                    with connect(settings.database_path) as conn:
                        old = conn.execute("SELECT * FROM watched_files WHERE path=?", (resolved,)).fetchone()
                        if old and old["size"] == stat.st_size and old["mtime_ns"] == stat.st_mtime_ns:
                            if old["processed"]:
                                continue
                            elapsed = (datetime.fromisoformat(ingestion.now()) - datetime.fromisoformat(old["observed_at"])).total_seconds()
                            if elapsed < settings.file_stable_seconds:
                                continue
                        else:
                            conn.execute("""INSERT INTO watched_files(path,size,mtime_ns,observed_at,processed) VALUES (?,?,?,?,0)
                                ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns,observed_at=excluded.observed_at,
                                document_id=NULL,error_code=NULL,processed=0""", (resolved, stat.st_size, stat.st_mtime_ns, ingestion.now()))
                            if settings.file_stable_seconds:
                                continue
                    if stat.st_size > MAX_DOCUMENT_BYTES:
                        raise DomainError("document_too_large", "Inbox file exceeds the supported size.", 413)
                    data = await asyncio.to_thread(read_inbox_file, path)
                    after = path.stat()
                    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                        continue
                    document, _ = ingestion.register_upload(settings, kind, path.name, mimetypes.guess_type(path.name)[0] or "application/octet-stream", data)
                    with connect(settings.database_path) as conn:
                        conn.execute("UPDATE watched_files SET processed=1,document_id=?,error_code=NULL WHERE path=?", (document["id"], resolved))
                except DomainError as exc:
                    with connect(settings.database_path) as conn:
                        conn.execute("UPDATE watched_files SET processed=1,error_code=? WHERE path=?", (exc.code, str(path.resolve())))
                except OSError:
                    continue  # A copy/rename in progress is retried on the next scan.

    async def cycle(self, as_of=None):
        settings = self.settings
        with connect(settings.database_path) as conn:
            self.check_lease(conn)
            if not conn.execute("SELECT 1 FROM restaurant LIMIT 1").fetchone():
                conn.execute("UPDATE worker_leases SET error_code='restaurant_not_configured' WHERE owner=?", (self.owner,))
                return
        await self.scan_inbox()
        with connect(settings.database_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.check_lease(conn)
            exhaust_abandoned_jobs(conn, settings.extraction_max_attempts)
            rows = conn.execute("""SELECT DISTINCT j.document_id FROM processing_jobs j JOIN documents d ON d.id=j.document_id
                WHERE j.kind='extract_document' AND j.status IN ('pending','processing') AND d.status IN ('detected','processing')
                AND (j.available_at IS NULL OR j.available_at<=?) AND (j.lease_until IS NULL OR j.lease_until<=?)
                ORDER BY j.created_at,j.id LIMIT 1""", (ingestion.now(), ingestion.now())).fetchall()
        for row in rows:
            await ingestion.process_document(self.app, row["document_id"])
        with connect(settings.database_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.check_lease(conn)
            owner = ingestion.restaurant_record(conn)
            as_of = as_of or analytics.local_today(owner)
            state = dict(conn.execute("SELECT key,value FROM worker_state").fetchall())
            policy = json.dumps({k: getattr(settings, k) for k in ["price_spike_pct", "projected_cost_increase_usd", "sales_drop_pct", "sales_drop_min_units", "sales_alert_recent_days"]}, sort_keys=True)
            if state.get("data_version") != str(owner["data_version"]) or state.get("as_of") != as_of.isoformat() or state.get("detector_policy") != policy:
                forecast = forecasting.calculate(conn, ForecastRequest(as_of=as_of))
                detectors.run_detectors(conn, settings, as_of, forecast)
                for key, value in [("data_version", owner["data_version"]), ("as_of", as_of.isoformat()), ("detector_policy", policy)]:
                    set_state(conn, key, value)
            else:
                detectors.detect_quality(conn)
            conn.execute("UPDATE worker_leases SET error_code=NULL,heartbeat_at=?,expires_at=? WHERE owner=?", (ingestion.now(), later(30), self.owner))
        await enrich_alerts(self.client, settings, limit=1)


async def run(settings, once=False):
    async with Worker(settings) as worker:
        print("MarginGuard worker running (durable queue, inbox scan, forecasts and alerts).", flush=True)
        while True:
            try:
                await worker.cycle()
            except DomainError as exc:
                if exc.code == "worker_lease_lost":
                    raise
                print(f"Worker cycle deferred: {exc.code}", flush=True)
            except (OSError, ValueError, ArithmeticError, sqlite3.Error, httpx.HTTPError):
                with connect(settings.database_path) as conn:
                    conn.execute("UPDATE worker_leases SET error_code='worker_cycle_failed' WHERE owner=?", (worker.owner,))
                print("Worker cycle failed; pending work remains durable for retry.", flush=True)
            if once:
                return
            await asyncio.sleep(settings.worker_poll_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one bounded worker cycle, then stop.")
    args = parser.parse_args()
    try:
        asyncio.run(run(Settings(), args.once))
    except KeyboardInterrupt:
        return 0
    except DomainError as exc:
        parser.exit(1, exc.message + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
