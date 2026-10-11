from pathlib import Path

from fitstat.config import load_config
from fitstat.db import connect
from fitstat.importer import import_client

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def demo_db():
    """База и конфиг тестового клиента «Демо» (tests/fixtures)."""
    cfg = load_config("demo", clients_dir=FIXTURES / "clients")
    conn = connect()
    counts = import_client(conn, cfg, FIXTURES / "raw" / "demo")
    return conn, cfg, counts
