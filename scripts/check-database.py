"""Check the configured database without printing credentials."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import settings
from sqlalchemy import create_engine, text

try:
    with create_engine(settings.database_url, connect_args={"connect_timeout": 10}).connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
    print("Supabase connection OK")
except Exception as exc:
    print(f"Database check failed: {type(exc).__name__}")
    # Driver errors describe DNS, transport, and authentication failures without
    # SQLAlchemy's exception URL or configuration values.
    message = str(getattr(exc, "orig", exc))
    from sqlalchemy.engine import make_url
    password = make_url(settings.database_url).password
    if password:
        message = message.replace(password, "***")
    print(message)
    sys.exit(1)
