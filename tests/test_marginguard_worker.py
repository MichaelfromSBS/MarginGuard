"""Persistent worker, restart, anomaly evidence and in-app notification boundaries."""
import asyncio
from datetime import date
import json
import shutil

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.config import ROOT, Settings
from backend.main import create_app
from backend.worker import Worker
from backend.marginguard.db import connect
from backend.marginguard.errors import DomainError
from backend.marginguard.extraction import ExtractionError
from backend.marginguard.fixture import ingest_fixture
from backend.marginguard.import_demo import import_demo
from backend.marginguard.ingestion import mark_problem
from backend.marginguard.jobs import claim_document
from backend.marginguard.schemas import InvoiceExtraction, ReceiptExtraction, WorkerStatus, Page, Alert

DAY = date(2026, 11, 7)
PAST = "2000-01-01T00:00:00+00:00"
DATA = ROOT / "demo_data"
INVOICE = "live_demo/2_invoice_RF-20261107-004"
RECEIPT = "live_demo/1_receipt_TB-20261107-001"


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    path = tmp_path_factory.mktemp("worker-baseline") / "history.db"
    import_demo(path)
    return path


@pytest.fixture
def settings(tmp_path, baseline):
    database = tmp_path / "worker.db"
    shutil.copy2(baseline, database)
    return Settings(_env_file=None, database_path=database, upload_directory=tmp_path / "uploads",
                    inbox_directory=tmp_path / "inbox", file_stable_seconds=0, alert_ai_explanations=False)


def expected(relative):
    value = json.loads((DATA / (relative + ".expected.json")).read_text())
    return (InvoiceExtraction if "invoice_number" in value else ReceiptExtraction).model_validate(value)


class Extractor:
    def __init__(self, *values):
        self.values, self.calls = list(values), 0

    async def __call__(self, *args):
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def upload(client, relative=INVOICE):
    response = client.post("/api/documents", data={"document_type": "invoice" if isinstance(expected(relative), InvoiceExtraction) else "receipt"},
                           files={"file": ((DATA / relative).name + ".pdf", (DATA / (relative + ".pdf")).read_bytes(), "application/pdf")})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def fixture(settings, relative):
    path = DATA / (relative + ".pdf")
    return ingest_fixture(settings, path, path.with_suffix(".expected.json"), "invoice")


def records(settings, table):
    with connect(settings.database_path) as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def test_api_only_queues_worker_processes_and_restarts_without_duplicate_records(settings):
    fake = Extractor(expected(INVOICE))
    with TestClient(create_app(settings)) as client:
        doc_id = upload(client)
        assert client.get(f"/api/documents/{doc_id}").json()["status"] == "detected"
        assert fake.calls == 0

        async def exercise():
            async with Worker(settings, extractor=fake) as worker:
                await worker.cycle(DAY)
                assert client.get(f"/api/documents/{doc_id}").json()["status"] == "completed"
                await worker.cycle(DAY)
            async with Worker(settings, extractor=fake) as worker:
                await worker.cycle(DAY)
        asyncio.run(exercise())
        assert upload(client) == doc_id
        assert fake.calls == 1
        assert len(records(settings, "invoices")) == 9
        assert len(records(settings, "alerts")) == 3
        assert len(records(settings, "notification_outbox")) == 0
        assert client.get("/api/dashboard?as_of=2026-11-07").json()["forecast"]["status"] == "ready"


def test_baseline_has_only_recent_complete_day_alert_and_invoice_reprices_automatically(settings):
    async def exercise():
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
            alerts = records(settings, "alerts")
            assert len(alerts) == 1 and alerts[0]["type"] == "unusual_sales"
            finding = json.loads(alerts[0]["finding_json"])
            assert finding["date"] == "2026-11-05" and finding["units"] == "39" and finding["baseline_units"] == "80.5"
            fixture(settings, INVOICE)
            await worker.cycle(DAY)
            alerts = records(settings, "alerts")
            price = json.loads(next(a for a in alerts if a["type"] == "ingredient_price_spike")["finding_json"])
            cost = json.loads(next(a for a in alerts if a["type"] == "projected_cost_increase")["finding_json"])
            assert price["increase_pct"] == "18" and price["base_unit"] == "lb"
            assert cost["increase"] == "730.17" and cost["previous_cost"] == "9413.63" and cost["current_cost"] == "10143.80"
            for relative in ["edge_cases/E3_pack_size_change_RF-20261107-005", "edge_cases/E5_late_arrival_RF-20261030-002"]:
                fixture(settings, relative)
                await worker.cycle(DAY)
            assert len(records(settings, "alerts")) == 3
            assert records(settings, "notification_outbox") == []
    asyncio.run(exercise())


def test_same_price_case_repack_before_startup_does_not_hide_the_original_spike(settings):
    fixture(settings, INVOICE)
    fixture(settings, "edge_cases/E3_pack_size_change_RF-20261107-005")
    async def exercise():
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
    asyncio.run(exercise())
    price = json.loads(next(a for a in records(settings, "alerts") if a["type"] == "ingredient_price_spike")["finding_json"])
    assert price["invoice_number"] == "RF-20261107-004" and price["increase_pct"] == "18"


def test_stable_inbox_copy_uses_same_queue_and_never_changes_original(settings):
    settings = settings.model_copy(update={"file_stable_seconds": 2})
    folder = settings.inbox_directory / "receipts"
    folder.mkdir(parents=True)
    path = folder / "incoming.pdf"
    source = (DATA / (RECEIPT + ".pdf")).read_bytes()
    path.write_bytes(source[:100])
    fake = Extractor(expected(RECEIPT))
    async def exercise():
        async with Worker(settings, extractor=fake) as worker:
            await worker.cycle(DAY)
            assert fake.calls == 0
            path.write_bytes(source)
            await worker.cycle(DAY)
            assert fake.calls == 0
            with connect(settings.database_path) as conn:
                conn.execute("UPDATE watched_files SET observed_at=?", (PAST,))
            await worker.cycle(DAY)
            await worker.cycle(DAY)
    asyncio.run(exercise())
    assert fake.calls == 1 and path.read_bytes() == source
    assert len(records(settings, "receipts")) == 2734
    receipt = records(settings, "receipts")[-1]
    assert receipt["local_date"] == "2026-11-07"
    assert not any(a["type"] == "unusual_sales" and '2026-11-07' in a["finding_json"] for a in records(settings, "alerts"))


def test_singleton_and_expired_document_claim_recovery(settings):
    fake = Extractor(expected(INVOICE))
    with TestClient(create_app(settings)) as client:
        doc = upload(client)
        async def exercise():
            async with Worker(settings) as worker:
                with pytest.raises(DomainError, match="already holds"):
                    async with Worker(settings):
                        pass
                with connect(settings.database_path) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    claim_document(conn, doc, 60)
                    conn.execute("UPDATE processing_jobs SET lease_until=? WHERE document_id=?", (PAST, doc))
            async with Worker(settings, extractor=fake) as restarted:
                await restarted.cycle(DAY)
        asyncio.run(exercise())
        assert client.get(f"/api/documents/{doc}").json()["status"] == "completed"
        assert fake.calls == 1


def test_active_claim_blocks_manual_retry_review_and_stale_failure_writes(settings):
    with TestClient(create_app(settings)) as client:
        doc = upload(client)
        with connect(settings.database_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = claim_document(conn, doc, 60)
        assert client.post(f"/api/documents/{doc}/process").status_code == 409
        assert client.post(f"/api/documents/{doc}/review", json={"document_type": "invoice", "extraction": expected(INVOICE).model_dump(mode="json")}).status_code == 409
        with connect(settings.database_path) as conn:
            conn.execute("UPDATE processing_jobs SET lease_until=? WHERE document_id=?", (PAST, doc))
            new = claim_document(conn, doc, 60)
        mark_problem(settings.database_path, doc, "obsolete_failure", "Must not overwrite the current attempt.", token=old["token"])
        job = records(settings, "processing_jobs")[-1]
        assert new["token"] != old["token"] and job["lease_owner"] == new["token"] and job["status"] == "processing"
        assert client.get(f"/api/documents/{doc}").json()["error_code"] is None


def test_cancelled_extraction_releases_claim_for_restart(settings):
    with TestClient(create_app(settings)) as client:
        doc = upload(client)
        async def exercise():
            entered = asyncio.Event()
            async def interrupted(*args):
                entered.set()
                await asyncio.Event().wait()
            async with Worker(settings, extractor=interrupted) as worker:
                task = asyncio.create_task(worker.cycle(DAY))
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert records(settings, "processing_jobs")[-1]["status"] == "pending"
            async with Worker(settings, extractor=Extractor(expected(INVOICE))) as worker:
                await worker.cycle(DAY)
        asyncio.run(exercise())
        assert client.get(f"/api/documents/{doc}").json()["status"] == "completed"
        assert len(records(settings, "invoices")) == 9


def test_transient_retries_are_bounded_and_explicit_retry_can_recover(settings):
    fake = Extractor(*[ExtractionError("provider_unavailable", "Provider unavailable.") for _ in range(3)], expected(INVOICE))
    with TestClient(create_app(settings)) as client:
        doc = upload(client)
        async def exercise():
            async with Worker(settings, extractor=fake) as worker:
                for attempt in range(3):
                    await worker.cycle(DAY)
                    job = records(settings, "processing_jobs")[-1]
                    assert job["attempts"] == attempt + 1
                    with connect(settings.database_path) as conn:
                        conn.execute("UPDATE processing_jobs SET available_at=? WHERE document_id=?", (PAST, doc))
                await worker.cycle(DAY)
                assert fake.calls == 3 and client.get(f"/api/documents/{doc}").json()["status"] == "failed"
                assert client.post(f"/api/documents/{doc}/process").status_code == 202
                await worker.cycle(DAY)
        asyncio.run(exercise())
        assert fake.calls == 4 and client.get(f"/api/documents/{doc}").json()["status"] == "completed"


def test_quality_alert_updates_once_and_resolves_after_approved_correction(settings):
    incomplete = expected(RECEIPT).model_copy(update={"channel_id": None})
    with TestClient(create_app(settings)) as client:
        doc = upload(client, RECEIPT)
        async def exercise():
            async with Worker(settings, extractor=Extractor(incomplete)) as worker:
                await worker.cycle(DAY)
                await worker.cycle(DAY)
                quality = next(a for a in records(settings, "alerts") if a["type"] == "data_quality")
                assert quality["revision"] == 1
                assert client.post(f"/api/documents/{doc}/review", json={"document_type": "receipt", "extraction": expected(RECEIPT).model_dump(mode="json"), "note": "Checked source channel."}).json()["status"] == "completed"
                await worker.cycle(DAY)
                quality = next(a for a in records(settings, "alerts") if a["type"] == "data_quality")
                assert quality["status"] == "resolved"
                assert records(settings, "notification_outbox") == []
        asyncio.run(exercise())


def test_worker_and_in_app_alert_status_are_honest(settings):
    with TestClient(create_app(settings)) as client:
        assert WorkerStatus.model_validate(client.get("/api/worker").json()).status == "not_started"
        async def exercise():
            async with Worker(settings) as worker:
                await worker.cycle(DAY)
                status = WorkerStatus.model_validate(client.get("/api/worker").json())
                assert status.status == "running" and status.new_alerts == 1
        asyncio.run(exercise())
        assert client.get("/api/worker").json()["status"] == "stopped"
        assert records(settings, "notification_outbox") == []


def test_in_app_acknowledgement_and_resolution_persist_across_worker_restart(settings):
    with TestClient(create_app(settings)) as client:
        async def exercise():
            async with Worker(settings) as worker:
                await worker.cycle(DAY)
            feed = Page[Alert].model_validate(client.get("/api/alerts?status=new").json())
            assert feed.total == 1
            alert = feed.items[0]
            assert client.post(f"/api/alerts/{alert.id}/acknowledge").json()["status"] == "acknowledged"
            assert client.post(f"/api/alerts/{alert.id}/acknowledge").json()["status"] == "acknowledged"
            assert client.get("/api/alerts?status=new").json()["total"] == 0
            async with Worker(settings) as worker:
                await worker.cycle(DAY)
            assert client.get("/api/alerts?status=new").json()["total"] == 0
            assert client.post(f"/api/alerts/{alert.id}/resolve").json()["status"] == "resolved"
            assert client.get("/api/alerts?status=resolved").json()["items"][0]["evidence"]
            assert len(records(settings, "alerts")) == 1 and records(settings, "notification_outbox") == []
        asyncio.run(exercise())


@pytest.mark.parametrize("reply", [httpx.Response(401, json={"error": "private-key-diagnostic"}),
    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"suggestion":"Raise all prices by 25 percent immediately."}'}}]})])
def test_ai_wording_failure_or_new_numbers_preserve_deterministic_finding(settings, reply):
    settings = Settings(_env_file=None, **{**settings.model_dump(), "ai_mode": "openrouter", "openrouter_api_key": "private-test-key", "openrouter_model": "test/model", "alert_ai_explanations": True})
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: reply)) as http:
            async with Worker(settings, client=http) as worker:
                await worker.cycle(DAY)
    asyncio.run(exercise())
    alert = records(settings, "alerts")[0]
    assert alert["explanation_status"] == "fallback" and "39 units" in alert["message"]
    assert "25 percent" not in alert["suggestion"]
    assert "private" not in json.dumps(records(settings, "alerts"))


def test_stale_worker_and_symlink_or_oversized_inputs_do_not_get_approved(settings):
    folder = settings.inbox_directory / "invoices"
    folder.mkdir(parents=True)
    path = folder / "oversized.pdf"
    with path.open("wb") as output:
        output.truncate(4 * 1024 * 1024 + 1)
    async def exercise():
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
            assert records(settings, "watched_files")[0]["error_code"] == "document_too_large"
            assert len(records(settings, "invoices")) == 8
            with connect(settings.database_path) as conn:
                conn.execute("UPDATE worker_leases SET expires_at=?", (PAST,))
            with TestClient(create_app(settings)) as client:
                assert client.get("/api/worker").json()["status"] == "stale"
            with pytest.raises(DomainError, match="expired"):
                await worker.cycle(DAY)
    asyncio.run(exercise())


def test_interrupted_extraction_attempt_budget_is_not_reset_by_worker_restart(settings):
    with TestClient(create_app(settings)) as client:
        doc = upload(client)
        with connect(settings.database_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            claim_document(conn, doc, 60)
            conn.execute("UPDATE processing_jobs SET attempts=3,lease_until=? WHERE document_id=?", (PAST, doc))
        fake = Extractor(expected(INVOICE))
        async def exercise():
            async with Worker(settings, extractor=fake) as worker:
                await worker.cycle(DAY)
        asyncio.run(exercise())
        assert fake.calls == 0
        result = client.get(f"/api/documents/{doc}").json()
        assert result["status"] == "failed" and result["error_code"] == "extraction_attempts_exhausted"


def test_sales_alert_is_resolved_when_coverage_is_no_longer_complete(settings):
    async def exercise():
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
            with connect(settings.database_path) as conn:
                conn.execute("UPDATE daily_coverage SET status='partial' WHERE date='2026-11-05' AND channel_id='delivery'")
                conn.execute("UPDATE restaurant SET data_version=data_version+1")
            await worker.cycle(DAY)
    asyncio.run(exercise())
    assert records(settings, "alerts")[0]["status"] == "resolved"


def test_accepted_ai_suggestion_never_replaces_measured_message(settings):
    settings = Settings(_env_file=None, **{**settings.model_dump(), "ai_mode": "openrouter", "openrouter_api_key": "test-key", "openrouter_model": "test/model", "alert_ai_explanations": True})
    reply = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"suggestion":"Check opening hours and recent promotions before attributing a cause."}'}}]})
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: reply)) as http:
            async with Worker(settings, client=http) as worker:
                await worker.cycle(DAY)
    asyncio.run(exercise())
    row = records(settings, "alerts")[0]
    assert row["explanation_status"] == "ai"
    assert "39 units" in row["message"] and "Check opening hours" in row["suggestion"]
