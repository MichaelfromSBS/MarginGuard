import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings
from .marginguard.db import initialize_database
from .marginguard.routes import DomainError, router as marginguard_router
from .marginguard.schemas import API_VERSION, ErrorDetail, ErrorResponse
from .marginguard.extraction import extract_document
from .worker import worker_status
from .marginguard.db import connect
from .marginguard.analytics import demo_clock


def create_app(settings: Settings | None = None, transport=None, document_extractor=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(settings.database_path)
        if settings.demo_as_of is not None:
            with connect(settings.database_path) as conn:
                owner = conn.execute("SELECT is_demo FROM restaurant LIMIT 1").fetchone()
                if owner is None or not owner["is_demo"]:
                    raise ValueError("A fixed demo date requires an explicitly fictional demo restaurant.")
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
                  description="Restaurant records, automatic forecasts, evidence-linked website alerts and read-only database-grounded owner chat. Monetary values and quantities are decimal strings.")

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
            error = ErrorResponse(error=ErrorDetail(code=code, message=message))
            return JSONResponse(error.model_dump(), status_code=status)

        # Block cross-site browser requests to the local paid API. CLI calls have no Origin.
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            allowed = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
            allowed.update(settings.allowed_origins)
            if origin and origin not in allowed:
                return reject("origin_not_allowed", "Origin is not allowed for this local development API.", 403)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 5_000_000):
                return reject("request_too_large", "Request too large (5 MB limit).", 413)
        token = demo_clock.set(settings.demo_as_of)
        try:
            return await call_next(request)
        finally:
            demo_clock.reset(token)

    @app.get("/api/health")
    async def health():
        with connect(settings.database_path) as conn:
            worker = worker_status(conn, settings)
        return {
            "status": "ok", "mode": settings.ai_mode,
            "api_version": API_VERSION, "checkpoint": 5, "database": "ready", "worker": worker["status"],
            "processing_mode": settings.processing_mode,
            "model": settings.openrouter_model if settings.ai_mode == "openrouter" else "mock-fixture",
            "configured": settings.ai_mode == "mock" or bool(settings.openrouter_api_key.get_secret_value().strip() and settings.openrouter_model.strip()),
            "demo_as_of": settings.demo_as_of,
        }

    app.include_router(marginguard_router)

    # After npm run build, the backend can serve the built UI from port 8000.
    if (ROOT / "frontend" / "dist").is_dir():
        app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="frontend")
    return app


app = create_app()
