"""Start the project's portable PostgreSQL only when .env selects it."""
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
PG_BIN = ROOT / '.tools' / 'postgresql' / 'pgsql' / 'bin'
PG_DATA = ROOT / 'data' / 'postgresql'
PORT = 55432


def start():
    url = make_url(os.environ.get('DATABASE_URL') or dotenv_values(ROOT / '.env')['DATABASE_URL'])
    if url.host not in {'127.0.0.1', 'localhost'} or url.port != PORT:
        return
    if not (PG_DATA / 'PG_VERSION').exists():
        raise RuntimeError('Local PostgreSQL is not initialized. See docs/local-postgresql.md.')
    ctl = str(PG_BIN / 'pg_ctl.exe')
    status = subprocess.run([ctl, '-D', str(PG_DATA), 'status'], capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if status.returncode == 0:
        return
    (ROOT / 'logs').mkdir(exist_ok=True)
    subprocess.run([ctl, '-D', str(PG_DATA), '-l', str(ROOT / 'logs' / 'postgresql.log'),
                    '-w', 'start'], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    print('Local PostgreSQL is ready on port 55432.')


if __name__ == '__main__':
    start()
