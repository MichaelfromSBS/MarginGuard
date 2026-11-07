import asyncio
import json
from collections.abc import AsyncIterator

import httpx
from pydantic import ValidationError

from .config import Settings
from .prompts import messages_for
from .schemas import Analysis, Finding, Evidence, RunRequest

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class AIError(Exception):
    """A safe error message suitable for the client; excludes raw provider payloads."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def headers(settings: Settings) -> dict:
    key = settings.openrouter_api_key.get_secret_value().strip()
    if not key or not settings.openrouter_model.strip():
        raise AIError("Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env, then restart the server.", 503)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def check_status(response: httpx.Response):
    code = response.status_code
    if code < 400:
        return
    messages = {
        400: "OpenRouter rejected the request. Check the model's schema/image support and input limits.",
        401: "OpenRouter rejected the API key. Check the server's .env file.",
        402: "OpenRouter credits are exhausted or the key's spending limit was reached.",
        403: "This API key or provider does not allow this request.",
        404: "The configured model or endpoint was not found.",
        429: "OpenRouter is rate-limiting requests. Wait briefly before retrying.",
    }
    raise AIError(messages.get(code, f"OpenRouter request failed (HTTP {code}). Try again later."), 502)


def payload_for(settings: Settings, request: RunRequest, *, structured: bool) -> dict:
    payload = {
        "model": settings.openrouter_model,
        "messages": messages_for(request, structured),
        "max_tokens": settings.ai_max_output_tokens,
    }
    if structured:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "analysis", "strict": True, "schema": Analysis.model_json_schema()},
        }
        # Don't silently route to a provider that ignores the requested schema.
        payload["provider"] = {"require_parameters": True}
    return payload


def mock_analysis(request: RunRequest) -> Analysis:
    # Intentionally a transparent fixture, not a fake intelligence implementation.
    findings = []
    for source in request.sources[:2]:
        findings.append(Finding(
            title=f"Source received: {source.title}",
            detail="Mock fixture: this confirms source plumbing only; no AI interpretation was performed.",
            evidence=[Evidence(source_id=source.id, quote=source.text[:120])],
        ))
    return Analysis(
        summary="MOCK OUTPUT — the pipeline is working. This fixture does not answer your task.",
        findings=findings,
        next_steps=["Choose a project, update the prompt/schema, then switch AI_MODE to openrouter."],
        unknowns=["Real model quality, latency, credits, and image support have not been tested."],
    )


async def analyze(client: httpx.AsyncClient, settings: Settings, request: RunRequest) -> tuple[Analysis, dict]:
    if settings.ai_mode == "mock":
        return mock_analysis(request), {}
    try:
        response = await client.post(API_URL, headers=headers(settings), json=payload_for(settings, request, structured=True))
        check_status(response)
        data = response.json()
        if data.get("error"):
            raise AIError("The provider returned an error. Check model availability, credits, and supported features.")
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise AIError("The model did not finish normally (limit, refusal, or tool request). Try a shorter input or higher output limit.")
        message = choice["message"]
        if message.get("refusal"):
            raise AIError("The model declined this request. Rephrase the task.")
        result = Analysis.model_validate_json(message["content"])
        return result, data.get("usage") or {}
    except httpx.TimeoutException as exc:
        raise AIError("The model timed out. Try a shorter request or a faster model.", 504) from exc
    except httpx.RequestError as exc:
        raise AIError("Could not reach OpenRouter. Check your internet connection.", 502) from exc
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        raise AIError("The model returned invalid structured output. Check schema support or simplify the task.") from exc


async def sse_data(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    """HTTPX handles split UTF-8/transport chunks; assemble SSE event data here."""
    parts: list[str] = []
    async for line in lines:
        if not line:
            if parts:
                yield "\n".join(parts)
                parts = []
        elif line.startswith("data:"):
            parts.append(line[5:].removeprefix(" "))
        # Comments, event, id and retry fields carry no completion text.
    if parts:
        yield "\n".join(parts)


async def stream_text(client: httpx.AsyncClient, settings: Settings, request: RunRequest) -> AsyncIterator[dict]:
    if settings.ai_mode == "mock":
        for word in "MOCK OUTPUT — streaming transport works. No AI analysis was performed. Configure OpenRouter to answer your task.".split(" "):
            await asyncio.sleep(0.025)
            yield {"type": "token", "text": word + " "}
        yield {"type": "done", "usage": {}}
        return
    payload = payload_for(settings, request, structured=False)
    payload.update(stream=True, stream_options={"include_usage": True})
    usage: dict = {}
    finished = False
    has_text = False
    try:
        async with client.stream("POST", API_URL, headers=headers(settings), json=payload) as response:
            check_status(response)
            async for raw in sse_data(response.aiter_lines()):
                if raw == "[DONE]":
                    if not finished or not has_text:
                        raise AIError("The provider ended the stream without a complete text answer.")
                    yield {"type": "done", "usage": usage}
                    return
                data = json.loads(raw)
                if data.get("error"):
                    raise AIError("The provider failed during streaming. Retry the request.")
                if data.get("usage"):
                    usage = data["usage"]
                for choice in data.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("refusal"):
                        raise AIError("The model declined this request.")
                    token = delta.get("content")
                    if isinstance(token, str) and token:
                        has_text = True
                        yield {"type": "token", "text": token}
                    reason = choice.get("finish_reason")
                    if reason == "stop":
                        finished = True
                    elif reason:
                        raise AIError("The stream ended early (output limit, refusal, or tool request).")
        raise AIError("The provider connection ended before the stream completed. Please retry.")
    except httpx.TimeoutException as exc:
        raise AIError("The model stream timed out.", 504) from exc
    except httpx.RequestError as exc:
        raise AIError("Connection to OpenRouter was interrupted.") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise AIError("The provider returned a malformed stream.") from exc
