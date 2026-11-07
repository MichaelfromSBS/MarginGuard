"""Business controls exercise actual v2 positive and negative fixtures."""
import json
from pathlib import Path

import pytest

from backend.config import ROOT
from backend.marginguard.schemas import InvoiceExtraction, ReceiptExtraction
from backend.marginguard.validation import validate_extraction

DATA = ROOT / "demo_data"
CATALOG = {
    "ingredients": [
        {"id": "beef", "base_unit": "lb"}, {"id": "bun", "base_unit": "each"},
        {"id": "produce", "base_unit": "each"}, {"id": "cheese", "base_unit": "each"},
        {"id": "veggie_patty", "base_unit": "each"},
    ],
    "dishes": [{"id": value} for value in ["classic_burger", "cheeseburger", "veggie_burger"]],
    "channels": [{"id": "in_store"}, {"id": "delivery"}],
}


def fixture(relative):
    path = DATA / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    kind = "invoice" if "invoice_number" in payload else "receipt"
    model = InvoiceExtraction if kind == "invoice" else ReceiptExtraction
    source = path.with_name(path.name.replace(".expected.json", ".txt")).read_text(encoding="utf-8")
    return model.model_validate(payload), kind, [source]


def checked(relative, **kwargs):
    extraction, kind, pages = fixture(relative)
    return validate_extraction(extraction, kind, CATALOG, pages, "America/New_York", **kwargs)


def codes(result):
    return {issue.code for issue in result.issues}


@pytest.mark.parametrize("relative", [
    *[path.relative_to(DATA).as_posix() for path in sorted((DATA / "history/invoices").glob("*.expected.json"))],
    "live_demo/1_receipt_TB-20261107-001.expected.json",
    "live_demo/2_invoice_RF-20261107-004.expected.json",
    "edge_cases/E3_pack_size_change_RF-20261107-005.expected.json",
    "edge_cases/E5_late_arrival_RF-20261030-002.expected.json",
])
def test_actual_positive_fixtures_validate(relative):
    result = checked(relative)
    assert result.is_valid, result.issues


def test_case_unit_cost_is_comparable_across_package_sizes():
    original = checked("live_demo/2_invoice_RF-20261107-004.expected.json")
    changed = checked("edge_cases/E3_pack_size_change_RF-20261107-005.expected.json")
    assert original.normalized_prices[0].unit_cost == changed.normalized_prices[0].unit_cost == "4.72"
    assert changed.normalized_prices[0].base_unit == "lb"


def test_unknown_vendor_and_ingredient_and_missing_case_size_have_distinct_reasons():
    result = checked("edge_cases/E4_needs_review_APC-20261107-01.expected.json")
    assert not result.is_valid
    assert {"unmapped_vendor", "unmapped_ingredient", "missing_pack_size"}.issubset(codes(result))
    assert result.normalized_prices == []


def test_unknown_dish_is_never_approved():
    result = checked("edge_cases/E4b_unknown_dish_TB-20261107-003.expected.json")
    assert not result.is_valid
    assert "unmapped_dish" in codes(result)


def test_invoice_reports_bad_line_subtotal_and_total():
    extraction, kind, pages = fixture("live_demo/2_invoice_RF-20261107-004.expected.json")
    changed_line = extraction.items[0].model_copy(update={"line_total": "95.00"})
    changed = extraction.model_copy(update={"items": [changed_line], "total": "95.00"})
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert {"invoice_line_amount_mismatch", "invoice_subtotal_mismatch", "invoice_total_mismatch"}.issubset(codes(result))


def test_quote_requires_membership_on_the_referenced_page_and_normalizes_whitespace():
    extraction, kind, pages = fixture("live_demo/2_invoice_RF-20261107-004.expected.json")
    wrapped = pages[0].replace("2 cases x 10 lb/case", "2 cases\n  x 10 lb/case")
    result = validate_extraction(extraction, kind, CATALOG, [wrapped], "America/New_York")
    assert result.is_valid
    wrong_quote = extraction.items[0].model_copy(update={"source_text": "This text was invented."})
    changed = extraction.model_copy(update={"items": [wrong_quote]})
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert "source_quote_mismatch" in codes(result)
    wrong_page = extraction.items[0].model_copy(update={"source_page": 2})
    changed = extraction.model_copy(update={"items": [wrong_page]})
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert "source_page_invalid" in codes(result)


def test_image_evidence_does_not_claim_independent_text_matching():
    extraction, kind, _ = fixture("live_demo/1_receipt_TB-20261107-001.expected.json")
    result = validate_extraction(extraction, kind, CATALOG, [], "America/New_York", image=True)
    assert result.is_valid, result.issues
    wrong_page = extraction.items[0].model_copy(update={"source_page": 2})
    changed = extraction.model_copy(update={"items": [wrong_page, extraction.items[1]]})
    result = validate_extraction(changed, kind, CATALOG, [], "America/New_York", image=True)
    assert "source_page_invalid" in codes(result)


def test_known_image_fixture_has_valid_financial_values():
    result = checked("live_demo/3_receipt_TB-20261107-002_photo.expected.json", image=True)
    assert result.is_valid, result.issues


@pytest.mark.parametrize("status", ["void", "refund"])
def test_refunds_and_voids_go_to_review_without_becoming_positive_sales(status):
    extraction, kind, pages = fixture("live_demo/1_receipt_TB-20261107-001.expected.json")
    result = validate_extraction(extraction.model_copy(update={"status": status}), kind, CATALOG, pages, "America/New_York")
    assert "unsupported_receipt_status" in codes(result)


def test_receipt_missing_channel_is_not_guessed():
    extraction, kind, pages = fixture("live_demo/1_receipt_TB-20261107-001.expected.json")
    result = validate_extraction(extraction.model_copy(update={"channel_id": None}), kind, CATALOG, pages, "America/New_York")
    assert "unmapped_channel" in codes(result)


def test_receipt_discount_allocation_reconciles_without_modifying_values():
    extraction, kind, pages = fixture("live_demo/1_receipt_TB-20261107-001.expected.json")
    first = extraction.items[0].model_copy(update={"discount_amount": "2.00", "net_amount": "22.00"})
    changed = extraction.model_copy(update={"discount": "2.00", "total": "37.96", "items": [first, extraction.items[1]]})
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert result.is_valid, result.issues
    bad = changed.model_copy(update={"discount": "1.00"})
    result = validate_extraction(bad, kind, CATALOG, pages, "America/New_York")
    assert {"receipt_discount_mismatch", "receipt_net_mismatch", "receipt_total_mismatch"}.issubset(codes(result))


def test_bad_receipt_line_gross_net_and_total_are_separate_findings():
    extraction, kind, pages = fixture("live_demo/1_receipt_TB-20261107-001.expected.json")
    first = extraction.items[0].model_copy(update={"gross_amount": "25.00", "net_amount": "23.00"})
    changed = extraction.model_copy(update={"items": [first, extraction.items[1]], "total": "1.00"})
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert {"receipt_line_amount_mismatch", "receipt_line_net_mismatch", "receipt_subtotal_mismatch", "receipt_net_mismatch", "receipt_total_mismatch"}.issubset(codes(result))


def test_weight_conversion_and_dimensional_mismatch():
    extraction, kind, pages = fixture("live_demo/2_invoice_RF-20261107-004.expected.json")
    item = extraction.items[0].model_copy(update={"quantity": "32", "purchase_unit": "oz", "pack_size": None, "pack_unit": None, "unit_price": "1", "line_total": "32"})
    changed = extraction.model_copy(update={"items": [item], "subtotal": "32", "total": "32"})
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert result.is_valid, result.issues
    assert result.normalized_prices[0].unit_cost == "16"
    wrong_dimension = item.model_copy(update={"ingredient_id": "bun"})
    result = validate_extraction(changed.model_copy(update={"items": [wrong_dimension]}), kind, CATALOG, pages, "America/New_York")
    assert "incompatible_unit" in codes(result)


def test_weight_purchase_and_extra_pack_size_is_ambiguous():
    extraction, kind, pages = fixture("live_demo/2_invoice_RF-20261107-004.expected.json")
    item = extraction.items[0].model_copy(update={"purchase_unit": "lb"})
    result = validate_extraction(extraction.model_copy(update={"items": [item]}), kind, CATALOG, pages, "America/New_York")
    assert "ambiguous_pack_unit" in codes(result)


def test_very_large_schema_valid_amounts_produce_review_not_a_decimal_crash():
    extraction, kind, pages = fixture("live_demo/2_invoice_RF-20261107-004.expected.json")
    item = extraction.items[0].model_copy(update={"quantity": "9" * 35})
    changed = InvoiceExtraction.model_validate(extraction.model_copy(update={"items": [item]}).model_dump())
    result = validate_extraction(changed, kind, CATALOG, pages, "America/New_York")
    assert "numeric_precision_exceeded" in codes(result)
    assert not result.normalized_prices


def test_document_kind_and_timezone_failures_are_safe():
    extraction, kind, pages = fixture("live_demo/1_receipt_TB-20261107-001.expected.json")
    assert "document_type_mismatch" in codes(validate_extraction(extraction, "invoice", CATALOG, pages, "America/New_York"))
    assert "invalid_restaurant_timezone" in codes(validate_extraction(extraction, kind, CATALOG, pages, "not/a-timezone"))


@pytest.mark.parametrize("relative,field,code", [
    ("live_demo/2_invoice_RF-20261107-004.expected.json", "invoice_number", "missing_invoice_number"),
    ("live_demo/2_invoice_RF-20261107-004.expected.json", "vendor_name", "missing_vendor_name"),
    ("live_demo/1_receipt_TB-20261107-001.expected.json", "receipt_number", "missing_receipt_number"),
])
def test_whitespace_only_business_identity_fields_require_review(relative, field, code):
    extracted, kind, pages = fixture(relative)
    payload = extracted.model_dump()
    payload[field] = " \t "
    # These values meet the string length constraint but are not usable identities.
    model = InvoiceExtraction if kind == "invoice" else ReceiptExtraction
    value = model.model_validate(payload)
    result = validate_extraction(value, kind, CATALOG, pages, "America/New_York")
    assert not result.is_valid
    assert code in codes(result)
