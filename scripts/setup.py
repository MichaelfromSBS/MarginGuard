"""Cross-platform setup. Run: python scripts/setup.py"""
import os
import argparse
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecasting', action='store_true', help='Include the optional scientific forecasting models.')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ is required.")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    node = shutil.which('node')
    if not npm or not node:
        raise SystemExit("Install Node.js 22.12+ (or a supported newer LTS), including npm, first.")
    version = subprocess.check_output([node, '--version'], text=True).strip().lstrip('v').split('.')
    if tuple(map(int, version[:2])) < (22, 12):
        raise SystemExit('Node.js 22.12+ is required. Update Node.js, then run setup again.')
    for port in (8000, 5173):
        with socket.socket() as connection:
            connection.settimeout(0.25)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is in use. Stop the development servers before setup; Windows locks running bundler files.")
    if not PYTHON.exists():
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    lock = "requirements-forecasting.lock.txt" if args.forecasting else "requirements.lock.txt"
    subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", lock], cwd=ROOT, check=True)
    subprocess.run([npm, "ci" if (ROOT / "package-lock.json").exists() else "install"], cwd=ROOT, check=True)
    if not (ROOT / ".env").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
    print("\nReady. Run: npm run dev\nThen open http://127.0.0.1:5173")


if __name__ == "__main__":
    main()
