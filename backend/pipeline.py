import time

import httpx

from .config import Settings
from .provider import analyze
from .schemas import Analysis, Metadata, RunRequest, RunResponse


def check_evidence(result: Analysis, request: RunRequest) -> list[str]:
    """Quote matching is a provenance check, not semantic fact checking."""
    sources = {source.id: source.text for source in request.sources}
    warnings = []
    for index, finding in enumerate(result.findings, start=1):
        if request.sources and not finding.evidence:
            warnings.append(f"Finding {index} has no text citation. Treat it as an unverified inference or visual observation.")
        for evidence in finding.evidence:
            if not evidence.quote.strip() or evidence.quote not in sources.get(evidence.source_id, ""):
                warnings.append(f"Finding {index}: quote does not match source '{evidence.source_id}'.")
    return warnings


async def run_pipeline(client: httpx.AsyncClient, settings: Settings, request: RunRequest) -> RunResponse:
    started = time.perf_counter()
    result, usage = await analyze(client, settings, request)
    warnings = check_evidence(result, request)
    if settings.ai_mode == "mock":
        warnings.insert(0, "Fixture mode: no model was called; the output is not task analysis.")
    return RunResponse(result=result, meta=Metadata(
        mode=settings.ai_mode,
        model=settings.openrouter_model if settings.ai_mode == "openrouter" else "mock-fixture",
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        usage=usage,
        warnings=warnings,
    ))
