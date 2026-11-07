"""Live checkpoint-1 read endpoints and explicit contracts for later checkpoints."""
import json
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from .db import connect
from .schemas import (
    API_VERSION, Alert, CapabilitiesResponse, CatalogResponse, ChatRequest,
    ChatResponse, Coverage, CoverageRequest, DashboardResponse, Document, DocumentDetail,
    DocumentStatus, DocumentType, ErrorResponse, ForecastResponse, IngredientPrice,
    Invoice, Page, Receipt, Restaurant, ReviewRequest,
)


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **details):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details


router = APIRouter(prefix="/api", tags=["MarginGuard v1"], responses={
    403: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
    404: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
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
    return {"api_version": API_VERSION, "checkpoint": 1, "capabilities": [
        {"name": name, "available": checkpoint == 1, "checkpoint": checkpoint}
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
        for item in page["items"]:
            item.pop("source_text", None)
        return page


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def document(document_id: str, request: Request):
    with connection(request) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise DomainError("document_not_found", "Document does not exist.", 404, document_id=document_id)
        return dict(row)


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
        for item in page["items"]:
            item["evidence"] = json.loads(item.pop("evidence_json"))
        return page


# Contract-first routes below deliberately do not accept/persist uploads, change
# business records, or fabricate metrics until their implementation checkpoint.
@router.post("/documents", response_model=Document, status_code=202)
def upload_document(document_type: Annotated[DocumentType, Form()], file: Annotated[UploadFile, File()]):
    unavailable(2, "Document ingestion")


@router.post("/documents/{document_id}/review", response_model=Document)
def review_document(document_id: str, body: ReviewRequest):
    unavailable(2, "Document review")


@router.post("/coverage/complete", response_model=Coverage)
def complete_coverage(body: CoverageRequest):
    unavailable(3, "Coverage updates")


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(start: date | None = None, end: date | None = None):
    if start and end and end < start:
        raise DomainError("invalid_period", "Period end precedes start.", 422)
    unavailable(3, "Dashboard metrics")


@router.get("/forecasts", response_model=Page[ForecastResponse])
def forecasts(limit: Limit = 50, offset: Offset = 0):
    unavailable(3, "Forecasting")


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert)
def acknowledge_alert(alert_id: str):
    unavailable(4, "Alert acknowledgement")


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    unavailable(5, "Database-backed chat")
