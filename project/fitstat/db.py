"""Схема базы отчётов (SQLite)."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE clubs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    opened_at TEXT NOT NULL
);
CREATE TABLE trainers (
    id INTEGER PRIMARY KEY,
    club_id INTEGER NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    club_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE visits (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    club_id INTEGER NOT NULL,
    visit_date TEXT NOT NULL,
    visit_type TEXT NOT NULL            -- regular | trial | guest_pass
);
CREATE TABLE sales (
    id INTEGER PRIMARY KEY,
    club_id INTEGER NOT NULL,
    person_id INTEGER,                  -- у продаж бара покупатель неизвестен
    sale_date TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- membership | personal_training | bar
    amount_kop INTEGER NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('own', 'partner'))
);
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    club_id INTEGER NOT NULL,
    trainer_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,
    sale_id INTEGER NOT NULL
);
"""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    return sqlite3.connect(path)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
