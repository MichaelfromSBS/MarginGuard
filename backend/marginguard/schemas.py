"""Version 1 wire contracts. Money and quantities are JSON strings, never floats."""
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

API_VERSION = "1.0.0"
DecimalString = Annotated[str, Field(pattern=r"^(0|[1-9]\d*)(\.\d{1,8})?$", max_length=40)]
SignedDecimalString = Annotated[str, Field(pattern=r"^-?(0|[1-9]\d*)(\.\d{1,8})?$", max_length=41)]
Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]
ShortText = Annotated[str, Field(min_length=1, max_length=300)]
Currency = Literal["USD"]
ChannelId = Literal["in_store", "delivery"]
Unit = Literal["lb", "oz", "each"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentType(StrEnum):
    invoice = "invoice"
    receipt = "receipt"


class DocumentStatus(StrEnum):
    detected = "detected"
    processing = "processing"
    completed = "completed"
    needs_review = "needs_review"
    failed = "failed"


class ErrorDetail(ContractModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    api_version: Literal["1.0.0"] = API_VERSION
    error: ErrorDetail


T = TypeVar("T")


class Page(ContractModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class Restaurant(ContractModel):
    id: Identifier
    name: str
    currency: Currency
    timezone: str
    data_version: int = Field(ge=0)
    is_demo: bool


class Ingredient(ContractModel):
    id: Identifier
    name: str
    base_unit: Unit
    aliases: list[str]


class IngredientPrice(ContractModel):
    id: Identifier
    ingredient_id: Identifier
    invoice_line_id: Identifier
    effective_date: date
    unit_cost: DecimalString
    base_unit: Unit


class Vendor(ContractModel):
    id: Identifier
    name: str
    aliases: list[str]


class Channel(ContractModel):
    id: ChannelId
    name: str
    fee_rate: DecimalString
    packaging_cost: DecimalString


class MenuPrice(ContractModel):
    id: Identifier
    channel_id: ChannelId
    price: DecimalString
    effective_date: date


class RecipeItem(ContractModel):
    id: Identifier
    ingredient_id: Identifier
    quantity: DecimalString
    unit: Unit


class RecipeVersion(ContractModel):
    id: Identifier
    effective_date: date
    items: list[RecipeItem]


class Dish(ContractModel):
    id: Identifier
    name: str
    prices: list[MenuPrice]
    recipes: list[RecipeVersion]


class CatalogResponse(ContractModel):
    source_data_version: int
    is_demo: bool
    ingredients: list[Ingredient]
    dishes: list[Dish]
    channels: list[Channel]
    vendors: list[Vendor] = Field(default_factory=list)


class Document(ContractModel):
    id: Identifier
    type: DocumentType
    filename: str
    sha256: str
    media_type: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    is_demo: bool
    error_code: str | None
    error_message: str | None


class DocumentDetail(Document):
    source_text: str | None
    page_count: int | None = None
    evidence_mode: Literal["text", "visual", "unavailable"] = "text"
    extraction_method: str | None = None
    extraction: dict | None = None
    validation_issues: list[dict] = Field(default_factory=list)
    reviewed_at: datetime | None = None
    review_note: str | None = None


class InvoiceItemInput(ContractModel):
    description: ShortText
    ingredient_id: Identifier | None
    quantity: DecimalString
    purchase_unit: Literal["lb", "oz", "each", "case"]
    pack_size: DecimalString | None
    pack_unit: Unit | None
    unit_price: DecimalString
    line_total: DecimalString
    source_page: int = Field(ge=1)
    source_text: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def usable_amounts(self):
        if Decimal(self.quantity) <= 0:
            raise ValueError("Quantity must be positive.")
        if self.pack_size is not None and Decimal(self.pack_size) <= 0:
            raise ValueError("Pack size must be positive.")
        if (self.pack_size is None) != (self.pack_unit is None):
            raise ValueError("Pack size and pack unit must be supplied together or both null.")
        # Unknown case size is allowed into the review schema, never silently inferred.
        return self


class InvoiceExtraction(ContractModel):
    vendor_id: Identifier | None
    vendor_name: ShortText
    invoice_number: ShortText
    invoice_date: date
    currency: Currency
    subtotal: DecimalString
    tax: DecimalString
    freight: DecimalString
    total: DecimalString
    items: list[InvoiceItemInput] = Field(min_length=1, max_length=200)


class InvoiceItem(InvoiceItemInput):
    id: Identifier


class Invoice(ContractModel):
    id: Identifier
    document_id: Identifier
    vendor_id: Identifier
    vendor_name: str
    invoice_number: str
    invoice_date: date
    currency: Currency
    subtotal: DecimalString
    tax: DecimalString
    freight: DecimalString
    total: DecimalString
    items: list[InvoiceItem]


class ReceiptItemInput(ContractModel):
    description: ShortText
    dish_id: Identifier | None
    quantity: DecimalString
    unit_price: DecimalString
    gross_amount: DecimalString
    discount_amount: DecimalString
    net_amount: DecimalString
    source_page: int = Field(ge=1)
    source_text: str = Field(min_length=1, max_length=4000)

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Quantity must be positive.")
        return value


class ReceiptExtraction(ContractModel):
    receipt_number: ShortText
    sold_at: datetime
    channel_id: ChannelId | None
    status: Literal["completed", "void", "refund"]
    currency: Currency
    subtotal: DecimalString
    discount: DecimalString
    tax: DecimalString
    tip: DecimalString
    total: DecimalString
    items: list[ReceiptItemInput] = Field(min_length=1, max_length=200)

    @field_validator("sold_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Sale timestamps require an explicit UTC offset.")
        return value


class ReceiptItem(ReceiptItemInput):
    id: Identifier


class Receipt(ContractModel):
    id: Identifier
    document_id: Identifier
    receipt_number: str
    sold_at: datetime
    local_date: date
    channel_id: ChannelId | None
    status: Literal["completed", "void", "refund"]
    currency: Currency
    subtotal: DecimalString
    discount: DecimalString
    tax: DecimalString
    tip: DecimalString
    total: DecimalString
    items: list[ReceiptItem]


class Coverage(ContractModel):
    date: date
    channel_id: ChannelId
    status: Literal["complete", "partial", "unknown", "closed"]
    updated_at: datetime


class EvidenceReference(ContractModel):
    kind: Literal["invoice_line", "receipt_item", "forecast_run", "document"]
    record_id: str
    document_id: str | None = None
    source_page: int | None = None
    quote: str | None = None


class Alert(ContractModel):
    id: Identifier
    event_key: str
    type: Literal["ingredient_price_spike", "projected_cost_increase", "unusual_sales", "data_quality"]
    severity: Literal["info", "warning", "critical"]
    status: Literal["new", "acknowledged", "resolved"]
    title: str
    message: str
    evidence: list[EvidenceReference]
    created_at: datetime
    updated_at: datetime


class Period(ContractModel):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.end < self.start:
            raise ValueError("Period end precedes start.")
        return self


class Metric(ContractModel):
    id: str
    label: str
    value: SignedDecimalString | None
    unit: Literal["USD", "units", "orders", "percent", "lb", "each"]
    kind: Literal["actual", "modeled", "projected"]
    period: Period | None
    as_of: datetime
    coverage: Literal["complete", "partial", "unknown", "insufficient_history"]
    source_data_version: int
    evidence: list[EvidenceReference]
    assumptions: list[str]


class ForecastResponse(ContractModel):
    id: Identifier
    status: Literal["pending", "ready", "insufficient_history", "failed"]
    horizon: Period
    method: str
    source_data_version: int
    created_at: datetime
    metrics: list[Metric]
    assumptions: list[str]


class DashboardResponse(ContractModel):
    api_version: Literal["1.0.0"] = API_VERSION
    restaurant: Restaurant
    as_of: datetime
    source_data_version: int
    metrics: list[Metric]
    forecast: ForecastResponse | None
    alerts: list[Alert]
    limitations: list[str]


class ChatRequest(ContractModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Question must not be blank.")
        return value.strip()


class ChatResponse(ContractModel):
    answer: str
    as_of: datetime
    metrics: list[Metric]
    evidence: list[EvidenceReference]
    limitations: list[str]


class InvoiceReview(ContractModel):
    document_type: Literal["invoice"]
    extraction: InvoiceExtraction
    note: str = Field(default="", max_length=2000)


class ReceiptReview(ContractModel):
    document_type: Literal["receipt"]
    extraction: ReceiptExtraction
    note: str = Field(default="", max_length=2000)


ReviewRequest = Annotated[InvoiceReview | ReceiptReview, Field(discriminator="document_type")]


class CoverageRequest(ContractModel):
    date: date
    channel_id: ChannelId
    status: Literal["complete", "closed"] = "complete"


class Capability(ContractModel):
    name: str
    available: bool
    checkpoint: int


class CapabilitiesResponse(ContractModel):
    api_version: Literal["1.0.0"] = API_VERSION
    checkpoint: Literal[2] = 2
    capabilities: list[Capability]
