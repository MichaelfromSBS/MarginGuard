"""Deterministic business validation for extracted invoices and sales receipts.

Schema validation establishes a wire shape; these checks decide whether that
shape is safe to approve into the ledger. Findings are review reasons, not
automatic corrections. Image quotations are visual evidence and cannot be
independently text-matched without a separate OCR transcription.
"""
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schemas import InvoiceExtraction, ReceiptExtraction

CENT = Decimal("0.01")
UNIT_PRECISION = Decimal("0.00000001")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    item_index: int | None = None


@dataclass(frozen=True)
class NormalizedPrice:
    item_index: int
    ingredient_id: str
    unit_cost: str
    base_unit: str


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized_prices: list[NormalizedPrice] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _matches_money(expected: Decimal, actual: str | Decimal) -> bool:
    """Compare source amounts to half-up cent arithmetic, allowing one cent."""
    return abs(expected.quantize(CENT, rounding=ROUND_HALF_UP) - Decimal(actual)) <= CENT


def _decimal_string(value: Decimal) -> str:
    # Unit costs retain fractional cents; only report/display amounts round to cents.
    result = format(value.quantize(UNIT_PRECISION, rounding=ROUND_HALF_UP), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _evidence(item, index: int, source_pages: list[str], image: bool, result: ValidationResult) -> None:
    if image:
        if item.source_page != 1:
            result.issues.append(ValidationIssue("source_page_invalid", "Image evidence must reference page 1.", index))
        return
    if item.source_page < 1 or item.source_page > len(source_pages):
        result.issues.append(ValidationIssue("source_page_invalid", "Evidence references a page outside the document.", index))
        return
    quote = _text(item.source_text)
    if not quote or quote not in _text(source_pages[item.source_page - 1]):
        result.issues.append(ValidationIssue("source_quote_mismatch", "Extracted source text does not occur on the referenced document page.", index))


def _unit_quantity(item, base_unit: str, index: int, result: ValidationResult) -> Decimal | None:
    quantity = Decimal(item.quantity)
    unit = item.purchase_unit
    if unit == "case" and (item.pack_size is None or item.pack_unit is None):
        result.issues.append(ValidationIssue("missing_pack_size", "A case requires an explicit pack quantity and unit before comparing prices.", index))
        return None
    if item.pack_size is not None:
        if unit in {"lb", "oz"}:
            result.issues.append(ValidationIssue("ambiguous_pack_unit", "A weight purchase unit with a separate pack size needs review to avoid counting its weight twice.", index))
            return None
        quantity *= Decimal(item.pack_size)
        unit = item.pack_unit
    if unit == base_unit and unit in {"lb", "oz", "each"}:
        return quantity
    if unit == "lb" and base_unit == "oz":
        return quantity * Decimal("16")
    if unit == "oz" and base_unit == "lb":
        return quantity / Decimal("16")
    result.issues.append(ValidationIssue("incompatible_unit", "Purchase units cannot be converted to this ingredient's catalog base unit.", index))
    return None


def _invoice(extraction: InvoiceExtraction, catalog: dict, source_pages: list[str], image: bool, result: ValidationResult) -> None:
    ingredients = {item["id"]: item for item in catalog.get("ingredients", [])}
    if not extraction.invoice_number.strip():
        result.issues.append(ValidationIssue("missing_invoice_number", "An approved invoice requires a nonblank invoice number."))
    if not extraction.vendor_name.strip():
        result.issues.append(ValidationIssue("missing_vendor_name", "An approved invoice requires a nonblank supplier name."))
    if extraction.vendor_id is None:
        result.issues.append(ValidationIssue("unmapped_vendor", "An approved invoice requires a reviewed supplier ID."))
    vendors = catalog.get("vendors")
    if extraction.vendor_id is not None and vendors and extraction.vendor_id not in {v["id"] for v in vendors}:
        result.issues.append(ValidationIssue("unknown_vendor", "Supplier ID is not in the configured vendor catalog."))
    subtotal = Decimal("0")
    for index, item in enumerate(extraction.items):
        _evidence(item, index, source_pages, image, result)
        line_total = Decimal(item.line_total)
        subtotal += line_total
        if not _matches_money(Decimal(item.quantity) * Decimal(item.unit_price), line_total):
            result.issues.append(ValidationIssue("invoice_line_amount_mismatch", "Invoice quantity times unit price does not reconcile to its line total.", index))
        ingredient = ingredients.get(item.ingredient_id)
        if ingredient is None:
            result.issues.append(ValidationIssue("unmapped_ingredient", "Invoice line does not map to a configured ingredient.", index))
            # Still surface a missing case weight independently of the mapping issue.
            if item.purchase_unit == "case" and (item.pack_size is None or item.pack_unit is None):
                result.issues.append(ValidationIssue("missing_pack_size", "A case requires an explicit pack quantity and unit before comparing prices.", index))
            continue
        amount = _unit_quantity(item, ingredient["base_unit"], index, result)
        if amount is not None:
            if amount <= 0:
                result.issues.append(ValidationIssue("invalid_quantity", "Normalized ingredient quantity must be positive.", index))
            else:
                result.normalized_prices.append(NormalizedPrice(index, item.ingredient_id, _decimal_string(line_total / amount), ingredient["base_unit"]))
    if not _matches_money(subtotal, extraction.subtotal):
        result.issues.append(ValidationIssue("invoice_subtotal_mismatch", "Invoice line amounts do not reconcile to the document subtotal."))
    expected_total = Decimal(extraction.subtotal) + Decimal(extraction.tax) + Decimal(extraction.freight)
    if not _matches_money(expected_total, extraction.total):
        result.issues.append(ValidationIssue("invoice_total_mismatch", "Invoice subtotal, tax and freight do not reconcile to the document total."))


def _receipt(extraction: ReceiptExtraction, catalog: dict, source_pages: list[str], image: bool, restaurant_timezone: str, result: ValidationResult) -> None:
    dishes = {item["id"] for item in catalog.get("dishes", [])}
    channels = {item["id"] for item in catalog.get("channels", [])}
    if not extraction.receipt_number.strip():
        result.issues.append(ValidationIssue("missing_receipt_number", "An approved receipt requires a nonblank receipt number."))
    if extraction.status != "completed":
        result.issues.append(ValidationIssue("unsupported_receipt_status", "Void and refund documents require review and are not approved as fresh positive sales."))
    if extraction.channel_id is None or extraction.channel_id not in channels:
        result.issues.append(ValidationIssue("unmapped_channel", "Sales channel is missing or is not configured; it must not be guessed."))
    try:
        # Explicit UTC input is valid too: normalize its instant rather than require
        # the source to have used the restaurant's local UTC offset already.
        extraction.sold_at.astimezone(ZoneInfo(restaurant_timezone))
    except (ZoneInfoNotFoundError, ValueError, OverflowError):
        result.issues.append(ValidationIssue("invalid_restaurant_timezone", "Restaurant timezone cannot be used to determine the local sales date."))
    gross_sum = Decimal("0")
    discount_sum = Decimal("0")
    net_sum = Decimal("0")
    for index, item in enumerate(extraction.items):
        _evidence(item, index, source_pages, image, result)
        if item.dish_id not in dishes:
            result.issues.append(ValidationIssue("unmapped_dish", "Receipt line does not map to a configured dish.", index))
        gross, discount, net = Decimal(item.gross_amount), Decimal(item.discount_amount), Decimal(item.net_amount)
        gross_sum += gross
        discount_sum += discount
        net_sum += net
        if not _matches_money(Decimal(item.quantity) * Decimal(item.unit_price), gross):
            result.issues.append(ValidationIssue("receipt_line_amount_mismatch", "Receipt quantity times unit price does not reconcile to its gross amount.", index))
        if discount > gross:
            result.issues.append(ValidationIssue("discount_exceeds_gross", "A line discount exceeds the gross item amount.", index))
        if not _matches_money(gross - discount, net):
            result.issues.append(ValidationIssue("receipt_line_net_mismatch", "Receipt gross amount minus allocated discount does not reconcile to its net amount.", index))
    if not _matches_money(gross_sum, extraction.subtotal):
        result.issues.append(ValidationIssue("receipt_subtotal_mismatch", "Receipt gross line amounts do not reconcile to the document subtotal."))
    if not _matches_money(discount_sum, extraction.discount):
        result.issues.append(ValidationIssue("receipt_discount_mismatch", "Allocated item discounts do not reconcile to the document discount."))
    expected_net = Decimal(extraction.subtotal) - Decimal(extraction.discount)
    if Decimal(extraction.discount) > Decimal(extraction.subtotal):
        result.issues.append(ValidationIssue("discount_exceeds_subtotal", "Document discount exceeds its item subtotal."))
    if not _matches_money(net_sum, expected_net):
        result.issues.append(ValidationIssue("receipt_net_mismatch", "Net line amounts do not reconcile to subtotal minus discount."))
    if not _matches_money(expected_net + Decimal(extraction.tax) + Decimal(extraction.tip), extraction.total):
        result.issues.append(ValidationIssue("receipt_total_mismatch", "Receipt net item amount, tax and tip do not reconcile to its charged total."))


def validate_extraction(
    extraction: InvoiceExtraction | ReceiptExtraction,
    document_type: str,
    catalog: dict,
    source_pages: list[str],
    restaurant_timezone: str,
    image: bool = False,
) -> ValidationResult:
    """Return all review findings and comparable prices without changing any data.

    Input must first pass its Pydantic extraction schema. This function performs
    no database writes, model calls, or inference of missing financial inputs.
    ``item_index`` values are zero-based. Normalized prices must be persisted
    only when the entire result is valid.
    """
    result = ValidationResult()
    try:
        with localcontext() as context:
            context.prec = 28
            if document_type == "invoice" and isinstance(extraction, InvoiceExtraction):
                _invoice(extraction, catalog, source_pages, image, result)
            elif document_type == "receipt" and isinstance(extraction, ReceiptExtraction):
                _receipt(extraction, catalog, source_pages, image, restaurant_timezone, result)
            else:
                result.issues.append(ValidationIssue("document_type_mismatch", "Document type does not match its extraction schema."))
    except DecimalException:
        result.issues.append(ValidationIssue("numeric_precision_exceeded", "Extracted numbers exceed the supported calculation precision and require review."))
        result.normalized_prices.clear()
    return result
