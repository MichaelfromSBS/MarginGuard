import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings
from .pipeline import run_pipeline
from .provider import AIError, stream_text
from .schemas import RunRequest, RunResponse
from .marginguard.db import initialize_database
from .marginguard.routes import DomainError, router as marginguard_router
from .marginguard.schemas import API_VERSION, ErrorDetail, ErrorResponse
from .marginguard.extraction import extract_document
from .worker import worker_status
from .marginguard.db import connect


def create_app(settings: Settings | None = None, transport=None, document_extractor=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(settings.database_path)
        app.state.database_path = settings.database_path
        app.state.settings = settings
        app.state.active_documents = set()
        app.state.document_extractor = document_extractor or extract_document
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.ai_timeout_seconds, connect=10), transport=transport,
        ) as client:
            app.state.client = client
            # Local development budget guard: do not accidentally fan out paid calls.
            app.state.ai_lock = asyncio.Lock()
            yield

    app = FastAPI(title="MarginGuard API", version=API_VERSION, lifespan=lifespan,
                  description="Checkpoint 4: durable document worker, metrics, automatic forecasts and evidence-based in-app alerts. No external owner notifications. Business chat remains checkpoint 5. Monetary values and quantities are decimal strings.")

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        error = ErrorResponse(error=ErrorDetail(code=exc.code, message=exc.message, details=exc.details))
        return JSONResponse(error.model_dump(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Avoid reflecting raw uploaded/business data into an error response.
        issues = [{"location": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()]
        error = ErrorResponse(error=ErrorDetail(code="validation_error", message="The request does not match the API contract.", details={"issues": issues}))
        return JSONResponse(error.model_dump(), status_code=422)

    @app.middleware("http")
    async def local_api_guard(request: Request, call_next):
        def reject(code: str, message: str, status: int):
            if request.url.path in {"/api/run", "/api/stream", "/api/health"}:
                return JSONResponse({"detail": message}, status_code=status)
            error = ErrorResponse(error=ErrorDetail(code=code, message=message))
            return JSONResponse(error.model_dump(), status_code=status)

        # Block cross-site browser requests to the local paid API. CLI calls have no Origin.
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            allowed = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
            if origin and origin not in allowed:
                return reject("origin_not_allowed", "Origin is not allowed for this local development API.", 403)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 5_000_000):
                return reject("request_too_large", "Request too large (5 MB limit).", 413)
        return await call_next(request)

    @app.exception_handler(AIError)
    async def ai_error_handler(request: Request, exc: AIError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.get("/api/health")
    async def health():
        with connect(settings.database_path) as conn:
            worker = worker_status(conn, settings)
        return {
            "status": "ok", "mode": settings.ai_mode,
            "api_version": API_VERSION, "checkpoint": 4, "database": "ready", "worker": worker["status"],
            "processing_mode": settings.processing_mode,
            "model": settings.openrouter_model if settings.ai_mode == "openrouter" else "mock-fixture",
            "configured": settings.ai_mode == "mock" or bool(settings.openrouter_api_key.get_secret_value().strip() and settings.openrouter_model.strip()),
        }

    @app.post("/api/run", response_model=RunResponse)
    async def run(body: RunRequest, request: Request):
        if app.state.ai_lock.locked():
            raise AIError("Another AI request is running. Wait or cancel it first.", 429)
        async with app.state.ai_lock:
            # Total timeout also covers slowly trickling responses.
            try:
                async with asyncio.timeout(settings.ai_timeout_seconds):
                    return await run_pipeline(request.app.state.client, settings, body)
            except TimeoutError as exc:
                raise AIError("The request exceeded the total time limit.", 504) from exc

    @app.post("/api/stream")
    async def stream(body: RunRequest, request: Request):
        if app.state.ai_lock.locked():
            raise AIError("Another AI request is running. Wait or cancel it first.", 429)

        async def events():
            async with app.state.ai_lock:
                try:
                    async with asyncio.timeout(settings.ai_timeout_seconds):
                        yield json.dumps({"type": "start", "mode": settings.ai_mode}) + "\n"
                        async for event in stream_text(request.app.state.client, settings, body):
                            if await request.is_disconnected():
                                return
                            yield json.dumps(event, ensure_ascii=False) + "\n"
                except AIError as exc:
                    yield json.dumps({"type": "error", "message": str(exc)}) + "\n"
                except TimeoutError:
                    yield json.dumps({"type": "error", "message": "The stream exceeded the total time limit."}) + "\n"

        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.include_router(marginguard_router)

    # After npm run build, the backend can serve the built UI from port 8000.
    if (ROOT / "frontend" / "dist").is_dir():
        app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="frontend")
    return app


app = create_app()
