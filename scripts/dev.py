"""Launch the API, independent worker and frontend without shell activation."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
VITE = ROOT / "node_modules" / "vite" / "bin" / "vite.js"


def main():
    if not PYTHON.exists() or not VITE.exists():
        raise SystemExit("Run python scripts/setup.py first.")
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is not on PATH.")
    processes = []
    code = 0
    try:
        api_command = [str(PYTHON), "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
        if sys.platform == "win32":
            # Proactor AcceptEx can close the listener after WinError 64.
            # Use Uvicorn's explicit loop factory, not a global asyncio policy.
            api_command += ["--loop", "asyncio:SelectorEventLoop"]
        processes.append(subprocess.Popen(api_command, cwd=ROOT))
        # Serve the UI only after the API is ready, so its first health check succeeds.
        deadline = time.monotonic() + 15
        while True:
            if processes[0].poll() is not None:
                raise SystemExit("The backend could not start. Check the output above.")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise SystemExit("The backend did not become ready within 15 seconds.")
            time.sleep(0.2)
        processes.append(subprocess.Popen([str(PYTHON), "-m", "backend.worker"], cwd=ROOT))
        processes.append(subprocess.Popen([node, str(VITE), "--config", "vite.config.ts"], cwd=ROOT / "frontend"))
        print("\nMarginGuard: http://127.0.0.1:5173 | API docs: http://127.0.0.1:8000/docs", flush=True)
        print("React edits reload automatically. Restart after backend or .env edits. Ctrl+C stops API, worker and frontend.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        failed = next(process.returncode for process in processes if process.returncode is not None)
        code = failed or 1
        print("A service stopped. Check the output above (ports 8000/5173 must be available).", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return code


if __name__ == "__main__":
    sys.exit(main())
