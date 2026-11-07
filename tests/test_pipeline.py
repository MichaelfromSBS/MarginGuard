import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


BODY = {
    "task": "Compare the notes and cite evidence.",
    "sources": [{"id": "brief", "title": "Brief", "text": "The demo starts at 4 PM."}],
}
RESULT = {
    "summary": "Check the demo time.",
    "findings": [{"title": "Demo time", "detail": "The brief gives a time.", "evidence": [{"source_id": "brief", "quote": "4 PM"}]}],
    "next_steps": ["Confirm the schedule."], "unknowns": ["Whether the brief is current."],
}


def live_settings(**kwargs):
    return Settings(_env_file=None, ai_mode="openrouter", openrouter_api_key="test-key-do-not-log", openrouter_model="test/model", **kwargs)


def client_for(handler, settings=None):
    return TestClient(create_app(settings or live_settings(), transport=httpx.MockTransport(handler)))


def completion(result=RESULT, **extra):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}], "usage": {"total_tokens": 42}, **extra})


def test_mock_runs_without_credentials_and_labels_fixture():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/health").json()["configured"]
        data = client.post("/api/run", json=BODY).json()
        assert data["meta"]["mode"] == "mock"
        assert "MOCK" in data["result"]["summary"]
        assert data["meta"]["warnings"]
        events = [json.loads(line) for line in client.post("/api/stream", json=BODY).text.splitlines()]
        assert events[0] == {"type": "start", "mode": "mock"}
        assert events[-1]["type"] == "done"


def test_structured_request_uses_schema_and_keeps_key_on_server():
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-key-do-not-log"
        payload = json.loads(request.content)
        assert payload["response_format"]["json_schema"]["strict"]
        assert payload["provider"]["require_parameters"]
        assert payload["messages"][0]["role"] == "system"
        assert payload["max_tokens"] == 1800
        return completion()

    with client_for(handler) as client:
        response = client.post("/api/run", json=BODY)
        assert response.status_code == 200
        assert response.json()["meta"]["warnings"] == []
        assert response.json()["meta"]["usage"]["total_tokens"] == 42
        assert "test-key" not in response.text
        assert "test-key" not in client.get("/api/health").text


def test_bad_quote_is_flagged_without_marking_claim_true():
    result = {**RESULT, "findings": [{"title": "Guess", "detail": "Unsupported", "evidence": [{"source_id": "missing", "quote": "5 PM"}]}]}
    with client_for(lambda _: completion(result)) as client:
        data = client.post("/api/run", json=BODY).json()
        assert "does not match" in data["meta"]["warnings"][0]


@pytest.mark.parametrize("invalid", [
    {}, {"summary": "missing fields"}, {**RESULT, "next_steps": "not a list"},
    {**RESULT, "unexpected_field": True},
])
def test_invalid_model_schema_fails_cleanly(invalid):
    with client_for(lambda _: completion(invalid)) as client:
        response = client.post("/api/run", json=BODY)
        assert response.status_code == 502
        assert "invalid structured" in response.json()["detail"]


@pytest.mark.parametrize("status, phrase", [(400, "support"), (401, "API key"), (402, "credits"), (429, "rate-limiting"), (503, "HTTP 503")])
def test_provider_http_errors_are_safe(status, phrase):
    with client_for(lambda _: httpx.Response(status, json={"error": {"message": "raw secret data must not escape"}})) as client:
        response = client.post("/api/run", json=BODY)
        assert response.status_code == 502
        assert phrase in response.json()["detail"]
        assert "raw secret" not in response.text


def test_http_200_error_is_not_a_success():
    with client_for(lambda _: httpx.Response(200, json={"error": {"message": "provider error"}})) as client:
        assert client.post("/api/run", json=BODY).status_code == 502


def test_timeout_is_reported():
    def handler(request):
        raise httpx.ReadTimeout("private diagnostic", request=request)
    with client_for(handler) as client:
        response = client.post("/api/run", json=BODY)
        assert response.status_code == 504
        assert "private diagnostic" not in response.text


def test_missing_credentials_do_not_fall_back_to_mock():
    settings = Settings(_env_file=None, ai_mode="openrouter")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["configured"] is False
        assert client.post("/api/run", json=BODY).status_code == 503


@pytest.mark.parametrize("patch", [
    {"task": "  "},
    {"sources": BODY["sources"] * 2},
    {"sources": [{"id": "a", "title": "a", "text": "x" * 32000}, {"id": "b", "title": "b", "text": "x" * 32000}, {"id": "c", "title": "c", "text": "x"}]},
    {"image": "https://example.com/image.jpg"},
    {"image": "data:image/png;base64,not-base64"},
])
def test_invalid_inputs_rejected(patch):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.post("/api/run", json={**BODY, **patch}).status_code == 422


def test_cross_origin_calls_blocked_and_same_origin_allowed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.post("/api/run", json=BODY, headers={"Origin": "https://other-site.example"}).status_code == 403
        assert client.post("/api/run", json=BODY, headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200


class ByteStream(httpx.AsyncByteStream):
    def __init__(self, text):
        self.data = text.encode("utf-8")

    async def __aiter__(self):
        # Deliberately split inside multibyte characters and SSE event delimiters.
        for byte in self.data:
            yield bytes([byte])


def chunk(data):
    return "data: " + json.dumps(data, ensure_ascii=False) + "\r\n\r\n"


def stream_client(content):
    return client_for(lambda _: httpx.Response(200, stream=ByteStream(content), headers={"Content-Type": "text/event-stream"}))


def events_for(client):
    return [json.loads(line) for line in client.post("/api/stream", json=BODY).text.splitlines()]


def test_stream_handles_unicode_comments_terminal_usage_and_done():
    content = ": heartbeat\r\n\r\n" + chunk({"choices": [{"delta": {"content": "你好 ☕"}, "finish_reason": None}]})
    content += chunk({"choices": [{"delta": {}, "finish_reason": "stop"}]})
    content += chunk({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"total_tokens": 9}})
    content += "data: [DONE]\r\n\r\n"
    with stream_client(content) as client:
        events = events_for(client)
        assert "".join(event.get("text", "") for event in events) == "你好 ☕"
        assert events[-1] == {"type": "done", "usage": {"total_tokens": 9}}


@pytest.mark.parametrize("content", [
    chunk({"error": {"message": "internal"}}),
    chunk({"choices": [{"delta": {"content": "partial"}, "finish_reason": "length"}]}),
    chunk({"choices": [{"delta": {"content": "partial"}, "finish_reason": None}]}),
    "data: [DONE]\n\n",
    "data: not-json\n\n",
])
def test_stream_failures_are_error_events_not_success(content):
    with stream_client(content) as client:
        events = events_for(client)
        assert events[-1]["type"] == "error"
        assert not any(event["type"] == "done" for event in events)
