"""Prepare and launch a separate, populated visitor demo: python scripts/demo.py."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
DEMO_ROOT = ROOT / 'data' / 'visitor-demo'
DEMO_DATE = '2026-11-07'


def demo_environment(live_ai=False, port=8000):
    env = {**os.environ,
           'MARGINGUARD_DATABASE_PATH': str(DEMO_ROOT / 'marginguard.db'),
           'MARGINGUARD_UPLOAD_DIRECTORY': str(DEMO_ROOT / 'uploads'),
           'MARGINGUARD_INBOX_DIRECTORY': str(DEMO_ROOT / 'inbox'),
           'MARGINGUARD_DEMO_AS_OF': DEMO_DATE,
           'MARGINGUARD_PROCESSING_MODE': 'worker',
           'MARGINGUARD_ALERT_AI_EXPLANATIONS': 'false',
           'AI_MODE': 'openrouter' if live_ai else 'mock',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
           'RAYON_NUM_THREADS': '1', 'UV_THREADPOOL_SIZE': '1'}
    if not live_ai:
        env['OPENROUTER_API_KEY'] = ''
        env['OPENROUTER_MODEL'] = ''
    origins = [f'http://127.0.0.1:{port}', f'http://localhost:{port}']
    name, domain = env.get('CODESPACE_NAME'), env.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN')
    if name and domain:
        origins.append(f'https://{name}-{port}.{domain}')
    env['MARGINGUARD_ALLOWED_ORIGINS'] = json.dumps(origins)
    return env


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def bootstrap(env, skip_setup=False):
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    lock_paths = [ROOT / name for name in ('requirements.lock.txt', 'requirements-forecasting.lock.txt', 'package-lock.json', 'scripts/setup.py')]
    expected = fingerprint(lock_paths)
    marker = DEMO_ROOT / 'setup.sha256'
    if not skip_setup and (not PYTHON.exists() or not (ROOT / 'node_modules/vite').exists() or not marker.exists() or marker.read_text() != expected):
        subprocess.run([sys.executable, str(ROOT / 'scripts/setup.py'), '--forecasting'], cwd=ROOT, env=env, check=True)
        marker.write_text(expected)
    if not PYTHON.exists():
        raise SystemExit('Run python scripts/setup.py --forecasting first.')
    sources = [*list((ROOT / 'frontend/src').rglob('*')), *list((ROOT / 'frontend/public').rglob('*')), ROOT / 'frontend/index.html', ROOT / 'frontend/vite.config.ts', ROOT / 'frontend/tsconfig.json', ROOT / 'package-lock.json']
    expected = fingerprint([p for p in sources if p.is_file()])
    marker = DEMO_ROOT / 'build.sha256'
    if not (ROOT / 'frontend/dist/index.html').exists() or not marker.exists() or marker.read_text() != expected:
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise SystemExit('Install Node.js 22.12+ including npm first.')
        subprocess.run([npm, 'run', 'build'], cwd=ROOT, env=env, check=True)
        marker.write_text(expected)


def prepare_database(settings):
    # Imported only after the virtual environment has been installed/re-entered.
    from datetime import date
    from backend.marginguard.db import connect
    from backend.marginguard.import_demo import import_demo
    from backend.marginguard.fixture import ingest_fixture
    from backend.marginguard import forecasting, detectors

    import_demo(settings.database_path)
    with connect(settings.database_path) as conn:
        initialized = conn.execute("SELECT value FROM worker_state WHERE key='visitor_demo_initialized'").fetchone()
        if initialized:
            return
        conn.execute('BEGIN IMMEDIATE')
        forecasting.calculate(conn, forecasting.default_request(conn, date.fromisoformat(DEMO_DATE)))
    for kind, stem in [('receipt', '1_receipt_TB-20261107-001'), ('invoice', '2_invoice_RF-20261107-004')]:
        source = ROOT / 'demo_data/live_demo' / stem
        ingest_fixture(settings, source.with_suffix('.pdf'), source.with_suffix('.expected.json'), kind)
    with connect(settings.database_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        forecast = forecasting.calculate(conn, forecasting.default_request(conn, date.fromisoformat(DEMO_DATE)))
        detectors.run_detectors(conn, settings, date.fromisoformat(DEMO_DATE), forecast)
        conn.execute("INSERT INTO worker_state(key,value) VALUES ('visitor_demo_initialized','1') ON CONFLICT(key) DO NOTHING")


def launch(settings, env, port, host, no_browser):
    processes = []
    try:
        command = [str(PYTHON), '-m', 'uvicorn', 'backend.main:app', '--host', host, '--port', str(port)]
        if sys.platform == 'win32':
            command += ['--loop', 'asyncio:SelectorEventLoop']
        processes.append(subprocess.Popen(command, cwd=ROOT, env=env))
        deadline = time.monotonic() + 30
        while True:
            if processes[0].poll() is not None:
                raise SystemExit('The demo API could not start. See the output above.')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=.5) as response:
                    health = json.load(response)
                    if health.get('demo_as_of') == DEMO_DATE:
                        break
            except (urllib.error.URLError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise SystemExit('The demo API did not start within 30 seconds.')
            time.sleep(.2)
        processes.append(subprocess.Popen([str(PYTHON), '-m', 'backend.worker'], cwd=ROOT, env=env))
        print(f'\nMarginGuard demo: http://127.0.0.1:{port}', flush=True)
        print(f'Fictional restaurant, fixed business date {DEMO_DATE}. Ctrl+C stops API and worker.', flush=True)
        if not no_browser and not env.get('CODESPACES'):
            webbrowser.open(f'http://127.0.0.1:{port}')
        while all(p.poll() is None for p in processes):
            time.sleep(.25)
        raise SystemExit('A demo service stopped. See the output above.')
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Install, build and populate without starting servers.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--live-ai', action='store_true', help='Opt in to configured OpenRouter credentials for extraction and chat.')
    parser.add_argument('--skip-setup', action='store_true', help='Use an already-installed development environment.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11+ is required.')
    if not 1024 <= args.port <= 65535:
        parser.error('Use a port between 1024 and 65535.')
    if not args.prepare_only:
        with socket.socket() as check:
            if check.connect_ex(('127.0.0.1', args.port)) == 0:
                parser.error(f'Port {args.port} is in use. Stop that server or choose --port 8016.')
    env = demo_environment(args.live_ai, args.port)
    bootstrap(env, args.skip_setup)
    if Path(sys.executable).resolve() != PYTHON.resolve():
        try:
            result = subprocess.run([str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:], '--skip-setup'], cwd=ROOT, env=env)
        except KeyboardInterrupt:
            return 0
        return result.returncode
    sys.path.insert(0, str(ROOT))
    from backend.config import Settings
    settings = Settings()
    if args.live_ai and not (settings.openrouter_api_key.get_secret_value().strip() and settings.openrouter_model.strip()):
        parser.error('Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env before using --live-ai.')
    # Apply only child/demo settings, never edit the owner's .env or normal database.
    settings = Settings(**{**settings.model_dump(),
        'database_path': Path(env['MARGINGUARD_DATABASE_PATH']), 'upload_directory': Path(env['MARGINGUARD_UPLOAD_DIRECTORY']),
        'inbox_directory': Path(env['MARGINGUARD_INBOX_DIRECTORY']), 'demo_as_of': DEMO_DATE,
        'ai_mode': env['AI_MODE'], 'allowed_origins': json.loads(env['MARGINGUARD_ALLOWED_ORIGINS'])})
    prepare_database(settings)
    print('Visitor demo prepared. Historical imports are explicit fixtures, not AI extraction.', flush=True)
    if not args.prepare_only:
        launch(settings, env, args.port, '0.0.0.0' if env.get('CODESPACES') else '127.0.0.1', args.no_browser)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
