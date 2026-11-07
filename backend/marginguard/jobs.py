"""Cross-process extraction claims. No network work takes place in transactions."""
from datetime import datetime, timedelta, timezone

from .ingestion import identifier, now


def later(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def active_claim(conn, document_id):
    return conn.execute("""SELECT 1 FROM processing_jobs WHERE document_id=? AND kind='extract_document'
        AND status='processing' AND lease_owner IS NOT NULL AND lease_until>? LIMIT 1""", (document_id, now())).fetchone() is not None


def claim_document(conn, document_id, timeout, maximum=3):
    stamp = now()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if doc is None or doc["status"] not in {"detected", "processing"} or active_claim(conn, document_id):
        return None
    job = conn.execute("""SELECT * FROM processing_jobs WHERE document_id=? AND kind='extract_document'
        AND status IN ('pending','processing') AND (available_at IS NULL OR available_at<=?)
        ORDER BY created_at,id LIMIT 1""", (document_id, stamp)).fetchone()
    if job is None or job["attempts"] >= maximum:
        return None
    token = identifier("claim")
    conn.execute("UPDATE processing_jobs SET status='processing',lease_owner=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=?",
                 (token, later(timeout + 60), stamp, job["id"]))
    conn.execute("UPDATE documents SET status='processing',updated_at=? WHERE id=?", (stamp, document_id))
    return {"token": token, "job_id": job["id"], "document": dict(doc), "attempts": job["attempts"] + 1}


def exhaust_abandoned_jobs(conn, maximum):
    rows = conn.execute("""SELECT id,document_id FROM processing_jobs WHERE kind='extract_document'
        AND status IN ('pending','processing') AND attempts>=? AND (lease_until IS NULL OR lease_until<=?)""", (maximum, now())).fetchall()
    for row in rows:
        message = "The extraction attempt limit was reached after interruption. Inspect the source and explicitly retry if appropriate."
        conn.execute("UPDATE processing_jobs SET status='failed',error_message=?,updated_at=? WHERE id=?", (message, now(), row["id"]))
        conn.execute("""UPDATE documents SET status='failed',error_code='extraction_attempts_exhausted',error_message=?,updated_at=?
            WHERE id=? AND status IN ('detected','processing')""", (message, now(), row["document_id"]))


def owns_claim(conn, token):
    return conn.execute("SELECT 1 FROM processing_jobs WHERE lease_owner=? AND status='processing' AND lease_until>?", (token, now())).fetchone() is not None


def release_claim(conn, token):
    row = conn.execute("SELECT document_id FROM processing_jobs WHERE lease_owner=? AND status='processing'", (token,)).fetchone()
    if row:
        conn.execute("UPDATE documents SET status='detected',updated_at=? WHERE id=? AND status='processing'", (now(), row["document_id"]))
        conn.execute("UPDATE processing_jobs SET status='pending',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE lease_owner=?", (now(), token))


def retry_transient(conn, claim, maximum, code):
    transient = {"extraction_timeout", "provider_connection_failed", "provider_rate_limited", "provider_unavailable", "provider_generation_failed"}
    if code not in transient or claim["attempts"] >= maximum:
        return
    # mark_problem has just recorded a safe failed result for this claimed job.
    job = conn.execute("SELECT * FROM processing_jobs WHERE id=? AND lease_owner=?", (claim["job_id"], claim["token"])).fetchone()
    if job and job["status"] == "failed":
        conn.execute("UPDATE processing_jobs SET status='pending',lease_owner=NULL,lease_until=NULL,available_at=?,updated_at=? WHERE id=?",
                     (later(min(300, 5 * 2 ** (claim["attempts"] - 1))), now(), claim["job_id"]))
        conn.execute("UPDATE documents SET status='detected',updated_at=? WHERE id=? AND status='failed'", (now(), claim["document"]["id"]))
