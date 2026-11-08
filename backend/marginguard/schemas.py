"""Version 1 wire contracts. Money and quantities are JSON strings, never floats."""
from datetime import date, datetime
from datetime import date as CalendarDate
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
    finding: dict = Field(default_factory=dict)
    suggestion: str = ""
    explanation_status: Literal["pending", "ai", "fallback"] = "pending"
    calculation_version: str = "detectors_v1"
    revision: int = 1


class WorkerStatus(ContractModel):
    status: Literal["running", "stopped", "stale", "not_started"]
    heartbeat_at: datetime | None
    error_code: str | None
    processing_mode: Literal["worker", "inline"]
    queued_documents: int
    processing_documents: int
    new_alerts: int
    watched_file_errors: int


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
    unit: Literal["USD", "units", "orders", "percent", "lb", "oz", "each"]
    kind: Literal["actual", "modeled", "projected"]
    period: Period | None
    as_of: datetime
    coverage: Literal["complete", "partial", "unknown", "insufficient_history"]
    source_data_version: int
    evidence: list[EvidenceReference]
    assumptions: list[str]


class CoverageSummary(ContractModel):
    period: Period
    complete: int
    partial: int
    unknown: int
    closed: int
    status: Literal["complete", "partial", "unknown"]
    days: list[Coverage]


class SalesGroup(ContractModel):
    date: CalendarDate | None = None
    dish_id: str | None = None
    channel_id: ChannelId | None = None
    units: DecimalString
    net_revenue: DecimalString
    orders: int


class SalesSummary(ContractModel):
    period: Period
    as_of: datetime
    source_data_version: int
    units: DecimalString
    net_revenue: DecimalString
    orders: int
    average_order_revenue: DecimalString | None
    coverage: CoverageSummary
    by_day: list[SalesGroup]
    by_dish: list[SalesGroup]
    by_channel: list[SalesGroup]
    evidence: list[EvidenceReference]
    evidence_truncated: bool
    assumptions: list[str]


class RecipeCostLine(ContractModel):
    ingredient_id: str
    name: str
    quantity: DecimalString
    base_unit: Unit
    unit_cost: DecimalString | None
    extended_cost: DecimalString | None
    price_effective_date: date | None
    evidence: EvidenceReference | None


class ChannelContribution(ContractModel):
    channel_id: ChannelId
    menu_price: DecimalString | None
    menu_price_id: str | None
    fee_rate: DecimalString
    packaging_cost: DecimalString
    contribution: SignedDecimalString | None
    contribution_margin_pct: SignedDecimalString | None


class DishCost(ContractModel):
    dish_id: str
    name: str
    as_of: date
    source_data_version: int
    recipe_version_id: str | None
    ingredient_cost: DecimalString | None
    ingredients: list[RecipeCostLine]
    channels: list[ChannelContribution]
    limitations: list[str]
    assumptions: list[str]


class ForecastRequest(ContractModel):
    method: Literal["weekday_average_v1", "regularized_poisson_v1", "poisson_gradient_boosting_v1", "recency_weekday_v1", "adaptive_ensemble_v1"] = "adaptive_ensemble_v1"
    as_of: date | None = None
    history_weeks: int = Field(default=8, ge=4, le=26)
    min_observations: int = Field(default=4, ge=4, le=26)
    sensitivity_pct: DecimalString = "15"

    @model_validator(mode="after")
    def valid_policy(self):
        if self.as_of is not None and not 1900 <= self.as_of.year <= 9998:
            raise ValueError("As-of year must be between 1900 and 9998.")
        if self.min_observations > self.history_weeks:
            raise ValueError("Minimum observations cannot exceed the history window in weeks.")
        if Decimal(self.sensitivity_pct) > 100:
            raise ValueError("Sensitivity must be between 0 and 100 percent.")
        return self


class WeekdayEstimate(ContractModel):
    weekday: int = Field(ge=0, le=6)
    sample_dates: list[date]
    mean_units: DecimalString | None


class ForecastSeries(ContractModel):
    dish_id: str
    channel_id: ChannelId
    status: Literal["ready", "insufficient_history", "missing_inputs"]
    units: DecimalString | None
    revenue: DecimalString | None
    ingredient_cost: DecimalString | None
    menu_price: DecimalString | None
    recipe_version_id: str | None
    weekday_estimates: list[WeekdayEstimate]
    limitations: list[str]


class ForecastDay(ContractModel):
    date: date
    dish_id: str
    channel_id: ChannelId
    is_open: bool
    units: DecimalString | None


class IngredientRequirement(ContractModel):
    ingredient_id: str
    quantity: DecimalString
    base_unit: Unit
    unit_cost: DecimalString
    cost: DecimalString
    evidence: EvidenceReference


class ForecastScenario(ContractModel):
    name: Literal["low", "base", "high"]
    volume_multiplier: DecimalString
    units: DecimalString
    revenue: DecimalString
    ingredient_cost: DecimalString


class ForecastEvaluation(ContractModel):
    status: Literal["ready", "insufficient_history"]
    holdout: Period
    observations: int
    weekday_average_mae: DecimalString | None
    seasonal_naive_mae: DecimalString | None
    selected_method: str | None = None
    selected_method_mae: DecimalString | None = None
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
    as_of: date | None = None
    training_period: Period | None = None
    training_coverage: CoverageSummary | None = None
    series: list[ForecastSeries] = Field(default_factory=list)
    daily: list[ForecastDay] = Field(default_factory=list)
    ingredients: list[IngredientRequirement] = Field(default_factory=list)
    scenarios: list[ForecastScenario] = Field(default_factory=list)
    evaluation: ForecastEvaluation | None = None
    limitations: list[str] = Field(default_factory=list)
    model_metadata: dict = Field(default_factory=dict)


class IngredientPriceOverride(ContractModel):
    ingredient_id: Identifier
    unit_cost: DecimalString


class MenuPriceOverride(ContractModel):
    dish_id: Identifier
    channel_id: ChannelId
    price: DecimalString


class PricingScenarioRequest(ContractModel):
    reference_date: date | None = None
    cost_pass_through_pct: DecimalString = "100"
    price_elasticity: SignedDecimalString = "-1"
    ingredient_prices: list[IngredientPriceOverride] = Field(default_factory=list, max_length=100)
    menu_prices: list[MenuPriceOverride] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid_scenario(self):
        if not -5 <= Decimal(self.price_elasticity) <= 0:
            raise ValueError("Price elasticity must be between -5 and 0.")
        if Decimal(self.cost_pass_through_pct) > 100:
            raise ValueError("Cost pass-through must be between 0 and 100 percent.")
        if any(Decimal(p.price) <= 0 for p in self.menu_prices):
            raise ValueError("Menu prices must be positive.")
        if len({p.ingredient_id for p in self.ingredient_prices}) != len(self.ingredient_prices):
            raise ValueError("Ingredient overrides must be unique.")
        if len({(p.dish_id, p.channel_id) for p in self.menu_prices}) != len(self.menu_prices):
            raise ValueError("Menu overrides must be unique per dish/channel.")
        return self


class PricingScenarioSeries(ContractModel):
    dish_id: str
    channel_id: ChannelId
    reference_unit_cost: DecimalString
    current_unit_cost: DecimalString
    scenario_unit_cost: DecimalString
    current_menu_price: DecimalString
    scenario_menu_price: DecimalString
    demand_multiplier: DecimalString
    baseline_units: DecimalString
    units: DecimalString
    revenue: DecimalString
    ingredient_cost: DecimalString


class PricingIngredientRequirement(IngredientRequirement):
    price_source: Literal["approved_invoice", "owner_assumption"]


class PricingScenarioResponse(ContractModel):
    forecast_id: str
    source_data_version: int
    horizon: Period
    reference_date: date
    price_elasticity: SignedDecimalString
    elasticity_source: Literal["owner_assumption"] = "owner_assumption"
    cost_pass_through_pct: DecimalString
    units: DecimalString
    revenue: DecimalString
    ingredient_cost: DecimalString
    revenue_less_ingredient_cost: SignedDecimalString
    fixed_demand_ingredient_cost: DecimalString
    series: list[PricingScenarioSeries]
    ingredients: list[PricingIngredientRequirement]
    assumptions: list[str]
    limitations: list[str]


class DashboardResponse(ContractModel):
    api_version: Literal["1.0.0"] = API_VERSION
    restaurant: Restaurant
    as_of: datetime
    source_data_version: int
    metrics: list[Metric]
    forecast: ForecastResponse | None
    alerts: list[Alert]
    limitations: list[str]
    sales: SalesSummary | None = None
    dish_costs: list[DishCost] = Field(default_factory=list)


class ChatMessage(ContractModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(ContractModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=6)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Question must not be blank.")
        return value.strip()


class ChatToolTrace(ContractModel):
    name: str
    arguments: dict
    metric_ids: list[str]
    status: Literal["ok", "unavailable"]


class ChatResponse(ContractModel):
    answer: str
    as_of: datetime
    metrics: list[Metric]
    evidence: list[EvidenceReference]
    limitations: list[str]
    status: Literal["answered", "clarification", "unsupported", "unavailable"] = "answered"
    source_data_version: int = 0
    answer_method: Literal["grounded_tools", "ai_explanation"] = "grounded_tools"
    tools: list[ChatToolTrace] = Field(default_factory=list)


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
    checkpoint: Literal[5] = 5
    capabilities: list[Capability]
