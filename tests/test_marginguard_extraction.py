import asyncio
from io import BytesIO
import json
from pathlib import Path

import httpx
from PIL import Image
from pypdf import PdfWriter
import pytest

from backend.config import ROOT, Settings
from backend.marginguard import document_io
from backend.marginguard.document_io import DocumentReadError, PreparedDocument, read_document
from backend.marginguard.extraction import ExtractionError, extract_document
from backend.marginguard.schemas import InvoiceExtraction, ReceiptExtraction

DEMO = ROOT / "demo_data/live_demo"
CATALOG = {"ingredients": [{"id": "beef", "name": "Ground beef", "base_unit": "lb"}], "dishes": [{"id": "classic_burger", "name": "Classic Burger"}]}


def settings(**kwargs):
    return Settings(_env_file=None, ai_mode="openrouter", openrouter_api_key="test-extraction-key", openrouter_model="test/model", **kwargs)


def expected(kind):
    filename = "2_invoice_RF-20261107-004.expected.json" if kind == "invoice" else "1_receipt_TB-20261107-001.expected.json"
    return json.loads((DEMO / filename).read_text())


def completion(value, **choice_extra):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}, **choice_extra}]})


def run_extraction(handler, *, kind="invoice", prepared=None, configured=None):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await extract_document(client, configured or settings(), kind, prepared or PreparedDocument("visible text", ["visible text"], 1, None), CATALOG, "America/New_York")
    return asyncio.run(execute())


@pytest.mark.parametrize("kind,model", [("invoice", InvoiceExtraction), ("receipt", ReceiptExtraction)])
def test_extraction_uses_typed_schema_and_does_not_return_credentials(kind, model):
    def handler(request):
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-extraction-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test/model"
        assert payload["response_format"]["json_schema"]["name"] == kind + "_extraction"
        assert payload["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        item_schema = payload["response_format"]["json_schema"]["schema"]["properties"]["items"]
        assert "maxItems" not in item_schema
        assert item_schema["minItems"] == 1
        assert model.model_json_schema()["properties"]["items"]["maxItems"] == 200
        assert payload["provider"]["require_parameters"] is True
        assert payload["max_tokens"] == settings().extraction_max_output_tokens
        assert "untrusted DATA" in payload["messages"][0]["content"]
        source = json.loads(payload["messages"][1]["content"][0]["text"])
        assert source["restaurant_timezone"] == "America/New_York"
        assert source["pages"] == [{"page": 1, "text": "visible text"}]
        assert source["catalog"] == CATALOG
        return completion(expected(kind))
    result = run_extraction(handler, kind=kind)
    assert isinstance(result, model)
    assert "test-extraction-key" not in result.model_dump_json()


@pytest.mark.parametrize("kind", ["invoice", "receipt"])
def test_item_limit_is_still_enforced_locally_after_provider_generation(kind):
    value = expected(kind)
    value["items"] = [value["items"][0]] * 201
    with pytest.raises(ExtractionError) as raised:
        run_extraction(lambda _: completion(value), kind=kind)
    assert raised.value.code == "invalid_extraction"


def test_image_payload_includes_source_bytes_without_inventing_ocr():
    prepared = PreparedDocument(None, [], 1, "data:image/png;base64,ZmFrZQ==")
    def handler(request):
        parts = json.loads(request.content)["messages"][1]["content"]
        assert parts[1] == {"type": "image_url", "image_url": {"url": prepared.image_data_url}}
        assert json.loads(parts[0]["text"])["pages"] == []
        return completion(expected("receipt"))
    assert isinstance(run_extraction(handler, kind="receipt", prepared=prepared), ReceiptExtraction)


@pytest.mark.parametrize("code,expected_code", [
    (400, "provider_request_rejected"), (401, "provider_authentication_failed"),
    (402, "provider_credits_exhausted"), (403, "provider_forbidden"),
    (404, "provider_model_not_found"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"),
])
def test_provider_failures_expose_only_safe_messages(code, expected_code):
    with pytest.raises(ExtractionError) as raised:
        run_extraction(lambda _: httpx.Response(code, json={"error": {"message": "private-source-and-secret"}}))
    assert raised.value.code == expected_code
    assert "private-source-and-secret" not in str(raised.value)
    assert "test-extraction-key" not in str(raised.value)


@pytest.mark.parametrize("response,expected_code", [
    (httpx.Response(200, json={"error": {"message": "internal"}}), "provider_generation_failed"),
    (httpx.Response(200, json=[]), "invalid_provider_response"),
    (httpx.Response(200, json={"choices": []}), "invalid_extraction"),
    (httpx.Response(200, content="not json"), "invalid_extraction"),
    (completion({"missing": "required fields"}), "invalid_extraction"),
    (completion(expected("invoice"), finish_reason="length"), "extraction_truncated"),
    (completion(expected("invoice"), finish_reason="tool_calls"), "extraction_incomplete"),
    (httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"refusal": "No", "content": ""}}]}), "model_refused"),
])
def test_incomplete_refused_or_malformed_output_is_never_approved(response, expected_code):
    with pytest.raises(ExtractionError) as raised:
        run_extraction(lambda _: response)
    assert raised.value.code == expected_code


def test_timeout_and_connection_failures_are_safe():
    def timeout(request):
        raise httpx.ReadTimeout("private diagnostic", request=request)
    with pytest.raises(ExtractionError) as raised:
        run_extraction(timeout)
    assert raised.value.code == "extraction_timeout"
    assert "private diagnostic" not in str(raised.value)

    def connection(request):
        raise httpx.ConnectError("private diagnostic", request=request)
    with pytest.raises(ExtractionError) as raised:
        run_extraction(connection)
    assert raised.value.code == "provider_connection_failed"


@pytest.mark.parametrize("configured,expected_code", [
    (Settings(_env_file=None, ai_mode="mock"), "live_model_required"),
    (Settings(_env_file=None, ai_mode="openrouter", openrouter_model="test/model", openrouter_api_key=""), "model_not_configured"),
    (Settings(_env_file=None, ai_mode="openrouter", openrouter_model="", openrouter_api_key="test-key"), "model_not_configured"),
])
def test_mock_and_missing_configuration_never_call_model(configured, expected_code):
    def must_not_call(_):
        pytest.fail("Mock/missing configuration must not send a paid request")
    with pytest.raises(ExtractionError) as raised:
        run_extraction(must_not_call, configured=configured)
    assert raised.value.code == expected_code


@pytest.mark.parametrize("kind,filename", [
    ("invoice", "2_invoice_RF-20261107-004.pdf"),
    ("receipt", "1_receipt_TB-20261107-001.pdf"),
])
def test_actual_v2_pdfs_read_strictly_and_preserve_evidence(kind, filename):
    prepared = read_document((DEMO / filename).read_bytes(), "application/pdf")
    assert prepared.page_count == 1
    assert prepared.image_data_url is None
    assert prepared.page_texts == [prepared.source_text]
    assert all(item["source_text"] in prepared.source_text for item in expected(kind)["items"])


def pdf_bytes(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize("data,media,code", [
    (b"", "application/pdf", "empty_document"),
    (b"anything", "text/plain", "unsupported_media_type"),
    (b"not-pdf", "application/pdf", "invalid_pdf"),
    (b"%PDF-1.4\nmalformed", "application/pdf", "invalid_pdf"),
    (b"x" * (4 * 1024 * 1024 + 1), "application/pdf", "document_too_large"),
    (pdf_bytes(), "application/pdf", "pdf_no_readable_text"),
    (pdf_bytes(pages=11), "application/pdf", "pdf_page_limit"),
    (pdf_bytes(password="private"), "application/pdf", "encrypted_pdf"),
])
def test_bad_or_unsupported_documents_fail_with_actionable_codes(data, media, code):
    with pytest.raises(DocumentReadError) as raised:
        read_document(data, media)
    assert raised.value.code == code


def test_pdf_text_and_stream_limits_are_enforced(monkeypatch):
    data = (DEMO / "1_receipt_TB-20261107-001.pdf").read_bytes()
    monkeypatch.setattr(document_io, "MAX_TEXT_CHARACTERS", 10)
    with pytest.raises(DocumentReadError) as raised:
        read_document(data, "application/pdf")
    assert raised.value.code == "pdf_text_limit"
    monkeypatch.setattr(document_io, "MAX_TEXT_CHARACTERS", 64000)
    monkeypatch.setattr(document_io, "MAX_PAGE_CONTENT_BYTES", 10)
    with pytest.raises(DocumentReadError) as raised:
        read_document(data, "application/pdf")
    assert raised.value.code == "pdf_content_limit"


def image_bytes(format="PNG", size=(16, 16)):
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize("format,media", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_images_are_decoded_without_claiming_verified_text(format, media):
    prepared = read_document(image_bytes(format), media)
    assert prepared.source_text is None
    assert prepared.page_texts == []
    assert prepared.page_count == 1
    assert prepared.image_data_url.startswith(f"data:{media};base64,")


def test_image_type_size_and_pixel_limits(monkeypatch):
    with pytest.raises(DocumentReadError) as raised:
        read_document(image_bytes("PNG"), "image/jpeg")
    assert raised.value.code == "image_type_mismatch"
    with pytest.raises(DocumentReadError) as raised:
        read_document(b"invalid pixels", "image/png")
    assert raised.value.code == "invalid_image"
    with pytest.raises(DocumentReadError) as raised:
        read_document(b"x" * (3 * 1024 * 1024 + 1), "image/png")
    assert raised.value.code == "image_too_large"
    monkeypatch.setattr(document_io, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(DocumentReadError) as raised:
        read_document(image_bytes(), "image/png")
    assert raised.value.code == "image_pixel_limit"
