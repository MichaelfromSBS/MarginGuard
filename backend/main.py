import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings
from .pipeline import run_pipeline
from .provider import AIError, stream_text
from .schemas import RunRequest, RunResponse


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.ai_timeout_seconds, connect=10), transport=transport,
        ) as client:
            app.state.client = client
            # Local development budget guard: do not accidentally fan out paid calls.
            app.state.ai_lock = asyncio.Lock()
            yield

    app = FastAPI(title="NOVA AI Starter", lifespan=lifespan)

    @app.middleware("http")
    async def local_api_guard(request: Request, call_next):
        # Block cross-site browser requests to the local paid API. CLI calls have no Origin.
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            allowed = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Origin is not allowed for this local development API."}, status_code=403)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 5_000_000):
                return JSONResponse({"detail": "Request too large (5 MB limit)."}, status_code=413)
        return await call_next(request)

    @app.exception_handler(AIError)
    async def ai_error_handler(request: Request, exc: AIError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok", "mode": settings.ai_mode,
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

    # After npm run build, the backend can serve the built UI from port 8000.
    if (ROOT / "frontend" / "dist").is_dir():
        app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="frontend")
    return app


app = create_app()
