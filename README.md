# NOVA AI Starter

A project-neutral React + TypeScript + FastAPI workspace. Prepared November 6, 2026, before NOVA. **Disclose this starter as pre-existing code when presenting.** See [PREEXISTING.md](PREEXISTING.md) for the preparation inventory and [docs/hackathon-plan.md](docs/hackathon-plan.md) for track advice and ideas.

## Start on this computer

Dependencies are installed in `.venv` and `node_modules`. From this folder:

```powershell
npm run dev
```

Open **http://127.0.0.1:5173**. API documentation: **http://127.0.0.1:8000/docs**. Use **Run workflow** with the included fictional example. Both structured cards and streaming text work without a key in **mock mode**, which explicitly returns a fixture rather than answering the task.

Ctrl+C stops both servers. React changes update automatically. Restart after editing Python or `.env`. The launcher binds only to your computer and fails if ports 8000/5173 are already in use.

If PowerShell blocks `npm.ps1`, use `npm.cmd run dev`. No global execution-policy changes are needed.

## First-time setup on your teammate's computer

Install Python 3.11+ and Node.js 22.12+ (or a supported newer LTS), including npm. Then:

```powershell
python scripts/setup.py
npm run dev
```

The setup script creates an isolated Python environment, installs the lockfiles, and copies `.env.example` to `.env` only if `.env` does not exist. Do not share `.venv` or `node_modules`; share the source and lockfiles. Existing environment variables override `.env` values.

Stop the development servers before rerunning setup. Windows locks the native bundler while it is running; setup checks the development ports before installing anything.

## Switch to the organizer's API key

The supplied tech guide says each team receives an OpenRouter key at the start. Edit the root `.env`:

```dotenv
AI_MODE=openrouter
OPENROUTER_API_KEY=your-team-key
OPENROUTER_MODEL=copy-a-current-model-id-from-openrouter
AI_TIMEOUT_SECONDS=60
AI_MAX_OUTPUT_TOKENS=1800
```

Choose a model endpoint that supports `structured_outputs`; for the optional image also check image input. IDs, availability, allowed models and prices can change, so there is intentionally no assumed default model. Check the [model catalog](https://openrouter.ai/models) and the team's key restrictions/credit allowance. Restart the server and run the included sample once. A configured badge only confirms configuration exists, not that a paid request succeeded.

**The real paid API path has not been tested with an actual key.** It is tested against mocked OpenRouter responses, including errors. Live mode never silently falls back to fixtures. Do not put keys in `VITE_*` variables, frontend code, screenshots, or Git. `.env` is ignored.

## What's ready

- Task + up to 8 pasted text sources, 64,000 total characters, and one optional image up to 3 MB.
- `POST /api/run`: input validation → prompt/context assembly → OpenRouter JSON Schema output → Pydantic validation → exact-quote checks → result + elapsed time + token usage.
- `POST /api/stream`: asynchronous OpenRouter SSE → normalized NDJSON → incremental browser text. Handles split Unicode, comments, incomplete streams, and provider error events.
- Browser cancellation, visible errors, export, responsive UI, no automatic retries or unbounded tool loops.
- One model request at a time and a configurable output cap/total timeout. These reduce accidental usage; they are **not a dollar budget**. Set spending controls on the team key.
- A local-only development API; it has no login or deployment configuration. Add authentication/rate limits before exposing it publicly.

Source quotes are checked for literal membership in the supplied text. Warnings flag mismatches, unknown source IDs and missing citations; this does **not** verify whether a quote logically supports a conclusion. Streaming text has no citation validation. Text is rendered as text, not executable HTML. Inputs stay in browser memory until refresh; this app does not persist them. In live mode, inputs go to OpenRouter and its selected provider.

## Make it your project

Start with these four files:

| File | Change |
| --- | --- |
| `backend/prompts.py` | Product behavior, task rules and context assembly |
| `backend/schemas.py` | Input and result contracts |
| `backend/pipeline.py` | Deterministic checks or one useful domain operation |
| `frontend/src/App.tsx` | Product-specific input and result interaction |

`backend/provider.py` contains the transport layer. `frontend/src/api.ts` defines matching frontend types; update them when changing the schema. Change fixtures and tests to match your product contract too. The provided fictional note-comparison sample exercises the template; it is not an implemented contradiction detector.

For six hours, begin with one model call and deterministic code around it. Add a database, vector search, MCP, audio, OCR, or agents only if the chosen user journey requires them. PDF/audio input, image generation, search and external actions are not implemented. Pasting extracted text is the supported document path.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run test:frontend
npm run build
```

On macOS/Linux use `.venv/bin/python -m pytest -q`. `requirements.lock.txt` and `package-lock.json` record the tested dependencies. The backend tests exercise mocked HTTP errors, malformed outputs, source checks, input validation and byte-split provider streams; frontend tests exercise the actual streaming parser.

To run the built UI and API on one port, build first and restart the backend:

```powershell
npm run build
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. For separate terminals with backend auto-reload, run `python -m uvicorn backend.main:app --reload` using the virtual environment, and `npm run dev --workspace frontend` in another terminal.

## References

The supplied organizer guides inform the stack and team-key workflow. Current official documentation checked November 6, 2026:

- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [OpenRouter streaming](https://openrouter.ai/docs/api/reference/streaming)
- [OpenRouter errors](https://openrouter.ai/docs/api/reference/errors-and-debugging)
- [HTTPX async requests](https://www.python-httpx.org/async/)
- [Vite setup](https://vite.dev/guide/)
