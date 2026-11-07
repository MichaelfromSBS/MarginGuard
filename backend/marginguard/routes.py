"""Checkpoint 4 APIs: durable ingestion, analytics, worker and alert delivery state."""
import json
import hashlib
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path

from .db import connect
from .errors import DomainError
from . import ingestion
from . import analytics, forecasting
from .detectors import alert_payload
from backend.worker import worker_status
from .schemas import (
    API_VERSION, Alert, CapabilitiesResponse, CatalogResponse, ChatRequest,
    ChatResponse, Coverage, CoverageRequest, DashboardResponse, Document, DocumentDetail,
    DocumentStatus, DocumentType, ErrorResponse, ForecastResponse, IngredientPrice,
    Invoice, Page, Receipt, Restaurant, ReviewRequest, ForecastRequest, SalesSummary, DishCost, WorkerStatus,
)


router = APIRouter(prefix="/api", tags=["MarginGuard v1"], responses={
    403: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
    404: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
    409: {"model": ErrorResponse}, 415: {"model": ErrorResponse},
    501: {"model": ErrorResponse},
})
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def connection(request: Request):
    return connect(request.app.state.database_path)


def page_query(conn, table: str, limit: int, offset: int, where="", params=(), order="id"):
    # Identifiers/order come only from this module, never from a query parameter.
    clause = " WHERE " + where if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM {table}" + clause, params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM {table}" + clause + f" ORDER BY {order} LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def unavailable(checkpoint: int, feature: str):
    raise DomainError("checkpoint_not_implemented", f"{feature} is planned for checkpoint {checkpoint}.", 501, checkpoint=checkpoint, feature=feature)


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    return {"api_version": API_VERSION, "checkpoint": 4, "capabilities": [
        {"name": name, "available": checkpoint <= 4, "checkpoint": checkpoint}
        for name, checkpoint in [
            ("catalog_and_seed_ledger", 1), ("document_ingestion", 2),
            ("metrics_and_forecasting", 3), ("background_processing_and_alerts", 4),
            ("database_backed_chat", 5),
        ]
    ]}


@router.get("/restaurant", response_model=Restaurant)
def restaurant(request: Request):
    with connection(request) as conn:
        row = conn.execute("SELECT * FROM restaurant ORDER BY id LIMIT 1").fetchone()
        if row is None:
            raise DomainError("restaurant_not_configured", "No restaurant is configured. Run the explicit demo seed command to load fictional examples.", 404)
        return dict(row)


@router.get("/catalog", response_model=CatalogResponse)
def catalog(request: Request):
    with connection(request) as conn:
        owner = conn.execute("SELECT data_version,is_demo FROM restaurant ORDER BY id LIMIT 1").fetchone()
        ingredients = []
        for row in conn.execute("SELECT * FROM ingredients ORDER BY id"):
            value = dict(row)
            value["aliases"] = json.loads(value.pop("aliases_json"))
            ingredients.append(value)
        dishes = []
        for row in conn.execute("SELECT * FROM dishes ORDER BY id"):
            value = dict(row)
            value["prices"] = [dict(p) for p in conn.execute("SELECT id,channel_id,price,effective_date FROM menu_prices WHERE dish_id=? ORDER BY effective_date,channel_id,id", (row["id"],))]
            recipes = []
            for version in conn.execute("SELECT id,effective_date FROM recipe_versions WHERE dish_id=? ORDER BY effective_date,id", (row["id"],)):
                recipe = dict(version)
                recipe["items"] = [dict(i) for i in conn.execute("SELECT id,ingredient_id,quantity,unit FROM recipe_items WHERE recipe_version_id=? ORDER BY id", (version["id"],))]
                recipes.append(recipe)
            value["recipes"] = recipes
            dishes.append(value)
        return {
            "source_data_version": owner["data_version"] if owner else 0,
            "is_demo": bool(owner["is_demo"]) if owner else False,
            "ingredients": ingredients, "dishes": dishes,
            "channels": [dict(row) for row in conn.execute("SELECT * FROM channels ORDER BY id")],
            "vendors": [{"id": r["id"], "name": r["name"], "aliases": json.loads(r["aliases_json"])} for r in conn.execute("SELECT * FROM vendors ORDER BY id")],
        }


@router.get("/ingredients/{ingredient_id}/prices", response_model=Page[IngredientPrice])
def ingredient_prices(ingredient_id: str, request: Request, limit: Limit = 50, offset: Offset = 0):
    with connection(request) as conn:
        if not conn.execute("SELECT 1 FROM ingredients WHERE id=?", (ingredient_id,)).fetchone():
            raise DomainError("ingredient_not_found", "Ingredient does not exist.", 404, ingredient_id=ingredient_id)
        return page_query(conn, "ingredient_prices", limit, offset, "ingredient_id=?", (ingredient_id,), "effective_date,id")


@router.get("/documents", response_model=Page[Document])
def documents(request: Request, limit: Limit = 50, offset: Offset = 0, document_type: DocumentType | None = None, status: DocumentStatus | None = None):
    clauses, params = [], []
    if document_type:
        clauses.append("type=?")
        params.append(document_type.value)
    if status:
        clauses.append("status=?")
        params.append(status.value)
    with connection(request) as conn:
        page = page_query(conn, "documents", limit, offset, " AND ".join(clauses), tuple(params), "created_at,id")
        page["items"] = [ingestion.document_payload(item) for item in page["items"]]
        return page


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def document(document_id: str, request: Request):
    return ingestion.get_document(request.app.state.database_path, document_id, detail=True)


@router.get("/documents/{document_id}/source", response_class=FileResponse)
def document_source(document_id: str, request: Request):
    with connection(request) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise DomainError("document_not_found", "Document does not exist.", 404)
        if not row["storage_path"]:
            raise DomainError("source_unavailable", "This fixture has persisted source text but no uploaded binary file.", 404)
        path = Path(row["storage_path"]).resolve()
        if not path.is_relative_to(request.app.state.settings.upload_directory.resolve()) or not path.is_file():
            raise DomainError("source_unavailable", "The stored source file is unavailable.", 404)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise DomainError("source_integrity_failed", "The stored source no longer matches the uploaded document hash.", 409)
        return FileResponse(path, media_type=row["media_type"], filename=row["filename"], content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/invoices", response_model=Page[Invoice])
def invoices(request: Request, limit: Limit = 50, offset: Offset = 0):
    with connection(request) as conn:
        page = page_query(conn, "invoices", limit, offset, order="invoice_date,id")
        for item in page["items"]:
            item["items"] = [dict(row) for row in conn.execute("SELECT id,description,ingredient_id,quantity,purchase_unit,pack_size,pack_unit,unit_price,line_total,source_page,source_text FROM invoice_lines WHERE invoice_id=? ORDER BY id", (item["id"],))]
        return page


@router.get("/receipts", response_model=Page[Receipt])
def receipts(request: Request, limit: Limit = 50, offset: Offset = 0, channel_id: Literal["in_store", "delivery"] | None = None):
    with connection(request) as conn:
        page = page_query(conn, "receipts", limit, offset, "channel_id=?" if channel_id else "", (channel_id,) if channel_id else (), "sold_at,id")
        for item in page["items"]:
            item["items"] = [dict(row) for row in conn.execute("SELECT id,description,dish_id,quantity,unit_price,gross_amount,discount_amount,net_amount,source_page,source_text FROM receipt_items WHERE receipt_id=? ORDER BY id", (item["id"],))]
        return page


@router.get("/coverage", response_model=Page[Coverage])
def coverage(request: Request, limit: Limit = 50, offset: Offset = 0):
    with connection(request) as conn:
        return page_query(conn, "daily_coverage", limit, offset, order="date,channel_id")


@router.get("/alerts", response_model=Page[Alert])
def alerts(request: Request, limit: Limit = 50, offset: Offset = 0, status: Literal["new", "acknowledged", "resolved"] | None = None):
    with connection(request) as conn:
        page = page_query(conn, "alerts", limit, offset, "status=?" if status else "", (status,) if status else (), "created_at,id")
        page["items"] = [alert_payload(item) for item in page["items"]]
        return page


@router.get("/worker", response_model=WorkerStatus)
def worker_health(request: Request):
    with connection(request) as conn:
        return worker_status(conn, request.app.state.settings)


@router.post("/documents", response_model=Document, status_code=202)
async def upload_document(request: Request, background_tasks: BackgroundTasks, response: Response,
                          document_type: Annotated[DocumentType, Form()], file: Annotated[UploadFile, File()]):
    try:
        data = await file.read(4 * 1024 * 1024 + 1)
        doc, duplicate = ingestion.register_upload(request.app.state.settings, document_type.value,
                                                   file.filename or "document", file.content_type, data)
    finally:
        await file.close()
    response.headers["X-MarginGuard-Duplicate"] = "true" if duplicate else "false"
    if not duplicate and request.app.state.settings.processing_mode == "inline":
        background_tasks.add_task(ingestion.process_document, request.app, doc["id"])
    return doc


@router.post("/documents/{document_id}/review", response_model=DocumentDetail)
def review_document(document_id: str, body: ReviewRequest, request: Request):
    return ingestion.review_document(request.app, document_id, body.extraction, body.note)


@router.post("/documents/{document_id}/process", response_model=Document, status_code=202)
def process_document(document_id: str, request: Request, background_tasks: BackgroundTasks):
    result = ingestion.queue_retry(request.app, document_id)
    if request.app.state.settings.processing_mode == "inline":
        background_tasks.add_task(ingestion.process_document, request.app, document_id)
    return result


@router.post("/coverage/complete", response_model=Coverage)
def complete_coverage(body: CoverageRequest, request: Request):
    with connection(request) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return analytics.complete_coverage(conn, body)


@router.get("/sales", response_model=SalesSummary)
def sales(request: Request, start: date | None = None, end: date | None = None,
          as_of: date | None = None, dish_id: str | None = None, channel_id: Literal["in_store", "delivery"] | None = None):
    with connection(request) as conn:
        conn.execute("BEGIN")
        owner = ingestion.restaurant_record(conn)
        start, end, _ = analytics.period_dates(owner, start, end, as_of)
        return analytics.sales_summary(conn, start, end, dish_id=dish_id, channel_id=channel_id)


@router.get("/dishes/{dish_id}/cost", response_model=DishCost)
def current_dish_cost(dish_id: str, request: Request, as_of: date | None = None):
    with connection(request) as conn:
        conn.execute("BEGIN")
        owner = ingestion.restaurant_record(conn)
        return analytics.dish_cost(conn, dish_id, as_of or analytics.local_today(owner))


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(request: Request, start: date | None = None, end: date | None = None, as_of: date | None = None):
    with connection(request) as conn:
        conn.execute("BEGIN")
        owner = ingestion.restaurant_record(conn)
        start, end, as_of = analytics.period_dates(owner, start, end, as_of)
        summary = analytics.sales_summary(conn, start, end)
        costs = [analytics.dish_cost(conn, r["id"], as_of) for r in conn.execute("SELECT id FROM dishes ORDER BY id").fetchall()]
        metrics = analytics.actual_metrics(summary)
        for cost in costs:
            metrics.append({"id": f"dish.{cost['dish_id']}.ingredient_cost", "label": f"{cost['name']} replacement ingredient cost",
                "value": cost["ingredient_cost"], "unit": "USD", "kind": "modeled", "period": None,
                "as_of": summary["as_of"], "coverage": "complete" if not cost["limitations"] else "unknown",
                "source_data_version": owner["data_version"], "evidence": [i["evidence"] for i in cost["ingredients"] if i["evidence"]],
                "assumptions": analytics.COST_ASSUMPTIONS})
        warnings = analytics.COST_ASSUMPTIONS + [issue for cost in costs for issue in cost["limitations"]]
        if summary["coverage"]["status"] != "complete":
            warnings.append("Sales are observed totals from incomplete coverage, not the restaurant's full-period sales.")
        forecast = forecasting.latest_forecast(conn, as_of)
        if forecast is None:
            warnings.append("No forecast has been calculated for this as-of date. POST /api/forecasts/recalculate to create one.")
        elif forecast.status == "pending":
            warnings.append("The saved forecast is stale; recalculate it after approved data or coverage changes.")
        alerts = []
        for row in conn.execute("SELECT * FROM alerts ORDER BY created_at DESC,id DESC LIMIT 20"):
            alerts.append(alert_payload(row))
        return {"restaurant": owner, "as_of": summary["as_of"], "source_data_version": owner["data_version"],
                "metrics": metrics, "forecast": forecast, "alerts": alerts, "limitations": warnings,
                "sales": summary, "dish_costs": costs}


@router.get("/forecasts", response_model=Page[ForecastResponse])
def forecasts(request: Request, limit: Limit = 50, offset: Offset = 0):
    with connection(request) as conn:
        conn.execute("BEGIN")
        return forecasting.list_forecasts(conn, limit, offset)


@router.post("/forecasts/recalculate", response_model=ForecastResponse)
def recalculate_forecast(body: ForecastRequest, request: Request):
    with connection(request) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return forecasting.calculate(conn, body)


@router.get("/forecasts/{run_id}", response_model=ForecastResponse)
def forecast_detail(run_id: str, request: Request):
    with connection(request) as conn:
        conn.execute("BEGIN")
        return forecasting.get_forecast(conn, run_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert)
def acknowledge_alert(alert_id: str, request: Request):
    return change_alert_status(request, alert_id, "acknowledged")


@router.post("/alerts/{alert_id}/resolve", response_model=Alert)
def resolve_alert(alert_id: str, request: Request):
    return change_alert_status(request, alert_id, "resolved")


def change_alert_status(request, alert_id, status):
    with connection(request) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if row is None:
            raise DomainError("alert_not_found", "Alert does not exist.", 404)
        if row["status"] != "resolved" and row["status"] != status:
            conn.execute("UPDATE alerts SET status=?,updated_at=? WHERE id=?", (status, ingestion.now(), alert_id))
        return alert_payload(conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone())


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    unavailable(5, "Database-backed chat")
