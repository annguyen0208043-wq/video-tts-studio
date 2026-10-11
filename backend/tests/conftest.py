import os
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(TEST_ROOT / 'data' / 'test-v2.db').as_posix()}")
os.environ.setdefault("DATA_DIR", str(TEST_ROOT / "data" / "test-runtime-v2"))
os.environ.setdefault("LOG_DIR", str(TEST_ROOT / "logs" / "test-runtime"))
