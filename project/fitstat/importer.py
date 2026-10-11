"""Импорт выгрузок из CRM клиента (raw/<client>/*.csv) в базу отчётов."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from fitstat.config import ROOT, ClientConfig
from fitstat.db import create_schema
from fitstat.money import to_kopecks

RAW_DIR = ROOT / "raw"


def _rows(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def _nullable_int(value: str) -> int | None:
    return int(value) if value else None


def import_client(conn: sqlite3.Connection, cfg: ClientConfig, raw_dir: Path | None = None) -> dict[str, int]:
    """Загружает выгрузку клиента в пустую базу. Возвращает число строк по таблицам."""
    raw_dir = raw_dir or RAW_DIR / cfg.slug
    create_schema(conn)
    partner_channels = set(cfg.partner_channels)

    def channel(raw_value: str) -> str:
        # В выгрузках каждого клиента свои названия каналов; приводим к own/partner
        return "partner" if raw_value in partner_channels else "own"

    tables = {
        "clubs": (
            "INSERT INTO clubs VALUES (?, ?, ?)",
            lambda r: (int(r["id"]), r["name"], r["opened_at"]),
        ),
        "trainers": (
            "INSERT INTO trainers VALUES (?, ?, ?)",
            lambda r: (int(r["id"]), int(r["club_id"]), r["name"]),
        ),
        "persons": (
            "INSERT INTO persons VALUES (?, ?, ?)",
            lambda r: (int(r["id"]), int(r["club_id"]), r["created_at"]),
        ),
        "visits": (
            "INSERT INTO visits VALUES (?, ?, ?, ?, ?)",
            lambda r: (int(r["id"]), int(r["person_id"]), int(r["club_id"]), r["visit_date"], r["visit_type"]),
        ),
        "sales": (
            "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?)",
            lambda r: (
                int(r["id"]),
                int(r["club_id"]),
                _nullable_int(r["person_id"]),
                r["sale_date"],
                r["kind"],
                to_kopecks(r["amount"]),
                channel(r["channel"]),
            ),
        ),
        # Колонка assistant_trainer_id в выгрузке есть, но пока не используется
        "sessions": (
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            lambda r: (
                int(r["id"]),
                int(r["club_id"]),
                int(r["trainer_id"]),
                int(r["person_id"]),
                r["session_date"],
                int(r["sale_id"]),
            ),
        ),
    }

    counts = {}
    for table, (sql, convert) in tables.items():
        rows = [convert(r) for r in _rows(raw_dir / f"{table}.csv")]
        conn.executemany(sql, rows)
        counts[table] = len(rows)
    conn.commit()
    return counts
