import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import ROOT, Settings
from backend.main import create_app
from backend.marginguard.schemas import (
    Alert, CapabilitiesResponse, CatalogResponse, Coverage, Document, DocumentDetail,
    ErrorResponse, IngredientPrice, Invoice, InvoiceExtraction, Page, Receipt,
    ReceiptExtraction, Restaurant,
)
from backend.marginguard.seed import seed_demo


@pytest.fixture
def seeded_client(tmp_path):
    path = tmp_path / "test.db"
    seed_demo(path)
    with TestClient(create_app(Settings(_env_file=None, database_path=path))) as client:
        yield client


def test_startup_migrates_but_never_automatically_seeds(tmp_path):
    path = tmp_path / "empty.db"
    with TestClient(create_app(Settings(_env_file=None, database_path=path))) as client:
        assert path.exists()
        assert client.get("/api/catalog").json() == {
            "source_data_version": 0, "is_demo": False, "ingredients": [], "dishes": [], "channels": [], "vendors": [],
        }
        response = client.get("/api/restaurant")
        assert response.status_code == 404
        assert ErrorResponse.model_validate(response.json()).error.code == "restaurant_not_configured"
        assert client.get("/api/documents").json()["total"] == 0


@pytest.mark.parametrize("path,model", [
    ("/api/restaurant", Restaurant), ("/api/catalog", CatalogResponse),
    ("/api/documents", Page[Document]), ("/api/documents/doc_invoice_beef_increase", DocumentDetail),
    ("/api/invoices", Page[Invoice]), ("/api/receipts", Page[Receipt]),
    ("/api/coverage", Page[Coverage]), ("/api/alerts", Page[Alert]),
    ("/api/ingredients/beef/prices", Page[IngredientPrice]),
    ("/api/capabilities", CapabilitiesResponse),
])
def test_read_routes_match_contract(seeded_client, path, model):
    response = seeded_client.get(path)
    assert response.status_code == 200, response.text
    model.model_validate(response.json())


def test_catalog_prices_recipes_and_seed_finances_are_exact_strings(seeded_client):
    catalog = seeded_client.get("/api/catalog").json()
    assert catalog["is_demo"]
    assert len(catalog["dishes"]) == 3
    classic = next(d for d in catalog["dishes"] if d["id"] == "classic_burger")
    assert all(p["price"] == "12.00" for p in classic["prices"])
    beef = next(i for i in classic["recipes"][0]["items"] if i["ingredient_id"] == "beef")
    assert beef["quantity"] == "0.50"
    history = seeded_client.get("/api/ingredients/beef/prices").json()["items"]
    assert [p["unit_cost"] for p in history] == ["4.00", "4.72"]
    for receipt in seeded_client.get("/api/receipts").json()["items"]:
        assert sum(Decimal(i["net_amount"]) for i in receipt["items"]) == Decimal(receipt["subtotal"]) - Decimal(receipt["discount"])
        assert Decimal(receipt["total"]) == Decimal(receipt["subtotal"]) - Decimal(receipt["discount"]) + Decimal(receipt["tax"]) + Decimal(receipt["tip"])
        assert datetime.fromisoformat(receipt["sold_at"]).utcoffset() is not None


def test_pagination_filters_and_total_are_consistent(seeded_client):
    first = seeded_client.get("/api/documents?document_type=invoice&limit=1&offset=0").json()
    second = seeded_client.get("/api/documents?document_type=invoice&limit=1&offset=1").json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert "source_text" not in first["items"][0]
    assert seeded_client.get("/api/documents?offset=99").json()["items"] == []
    assert seeded_client.get("/api/documents?status=needs_review").json()["total"] == 0
    assert seeded_client.get("/api/receipts?channel_id=delivery").json()["total"] == 1


@pytest.mark.parametrize("path", ["/api/documents/missing", "/api/ingredients/missing/prices"])
def test_unknown_resource_returns_typed_not_found(seeded_client, path):
    response = seeded_client.get(path)
    assert response.status_code == 404
    assert ErrorResponse.model_validate(response.json()).error.code.endswith("not_found")


@pytest.mark.parametrize("path", ["/api/documents?limit=0", "/api/documents?offset=-1", "/api/documents?status=garbage", "/api/receipts?channel_id=unknown"])
def test_query_validation_returns_typed_error(seeded_client, path):
    response = seeded_client.get(path)
    assert response.status_code == 422
    assert ErrorResponse.model_validate(response.json()).error.code == "validation_error"


@pytest.mark.parametrize("headers,status,code", [
    ({"Origin": "https://unrelated.example"}, 403, "origin_not_allowed"),
    ({"Content-Length": "5000001"}, 413, "request_too_large"),
])
def test_product_guard_errors_match_frontend_contract(seeded_client, headers, status, code):
    response = seeded_client.get("/api/catalog", headers=headers)
    assert response.status_code == status
    assert ErrorResponse.model_validate(response.json()).error.code == code


@pytest.mark.parametrize("path,checkpoint", [("/api/dashboard", 3), ("/api/forecasts", 3)])
def test_unimplemented_metrics_never_masquerade_as_live_results(seeded_client, path, checkpoint):
    response = seeded_client.get(path)
    assert response.status_code == 501
    error = ErrorResponse.model_validate(response.json()).error
    assert error.code == "checkpoint_not_implemented"
    assert error.details["checkpoint"] == checkpoint


def test_invalid_upload_and_future_write_routes_do_not_persist_records(seeded_client):
    count = seeded_client.get("/api/documents").json()["total"]
    response = seeded_client.post("/api/documents", data={"document_type": "invoice"}, files={"file": ("test.pdf", b"example", "application/pdf")})
    assert response.status_code == 415
    assert seeded_client.get("/api/documents").json()["total"] == count
    assert seeded_client.post("/api/chat", json={"question": "What were sales?"}).status_code == 501
    assert seeded_client.post("/api/coverage/complete", json={"date": "2026-11-07", "channel_id": "in_store"}).status_code == 501
    assert seeded_client.post("/api/alerts/test/acknowledge").status_code == 501
    data = json.loads((ROOT / "examples/invoice.expected.json").read_text())
    assert seeded_client.post("/api/documents/test/review", json={"document_type": "invoice", "extraction": data}).status_code == 404


def test_coverage_keeps_partial_and_unknown_days_distinct(seeded_client):
    data = seeded_client.get("/api/coverage").json()["items"]
    assert {r["status"] for r in data} == {"complete", "partial", "unknown"}
    assert seeded_client.get("/api/alerts").json()["total"] == 0


@pytest.mark.parametrize("name,model", [("invoice", InvoiceExtraction), ("receipt", ReceiptExtraction)])
def test_claude_handoff_fixtures_validate_and_quotes_exist(name, model):
    value = model.model_validate_json((ROOT / f"examples/{name}.expected.json").read_text())
    source = (ROOT / f"examples/{name}.txt").read_text()
    assert all(item.source_text in source for item in value.items)


def test_decimal_inputs_never_accept_binary_float_or_missing_timezone():
    data = json.loads((ROOT / "examples/receipt.expected.json").read_text())
    data["total"] = 39.96
    with pytest.raises(ValidationError):
        ReceiptExtraction.model_validate(data)
    data["total"] = "39.96"
    data["sold_at"] = "2026-11-07T12:30:00"
    with pytest.raises(ValidationError):
        ReceiptExtraction.model_validate(data)


def test_contract_openapi_covers_multipart_and_future_success_shapes(seeded_client):
    schema = seeded_client.get("/openapi.json").json()
    assert schema["info"]["version"] == "1.0.0"
    assert "multipart/form-data" in schema["paths"]["/api/documents"]["post"]["requestBody"]["content"]
    assert schema["paths"]["/api/dashboard"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("DashboardResponse")
    assert "501" in schema["paths"]["/api/dashboard"]["get"]["responses"]


def test_checkpoint_features_and_configuration_do_not_expose_credentials(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, database_path=tmp_path / "key.db", openrouter_api_key="private-test-value"))) as client:
        features = client.get("/api/capabilities").json()
        assert [f["name"] for f in features["capabilities"] if f["available"]] == ["catalog_and_seed_ledger", "document_ingestion"]
        assert "private-test-value" not in client.get("/api/health").text
        assert client.get("/api/health").json()["database"] == "ready"
