"""Run release checks in the project environment: python scripts/check.py."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def main():
    if not PYTHON.exists():
        raise SystemExit('Run python scripts/setup.py --forecasting first.')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise SystemExit('npm is not on PATH.')
    env = {**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
           'RAYON_NUM_THREADS': '1', 'UV_THREADPOOL_SIZE': '1'}
    # Keep large fixture databases on the project drive and remove only this run's files.
    workspace = (ROOT / '.venv').resolve()
    with tempfile.TemporaryDirectory(prefix='verify-', dir=workspace) as directory:
        temporary = Path(directory).resolve()
        if not temporary.is_relative_to(workspace):
            raise RuntimeError('Verification temporary directory must stay inside .venv.')
        env.update({key: str(temporary) for key in ('TEMP', 'TMP', 'TMPDIR')})
        for command in ([str(PYTHON), '-m', 'pytest', '-q', '--basetemp', str(temporary / 'pytest')],
                        [npm, 'run', 'test:frontend'], [npm, 'run', 'build'], [str(PYTHON), '-m', 'pip', 'check']):
            subprocess.run(command, cwd=ROOT, env=env, check=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
