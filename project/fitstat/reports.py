"""Ежемесячные отчёты по клубу, тренеру и сети.

Сигнатуры публичных функций не меняем: на них завязаны выгрузки клиентам.
"""
from __future__ import annotations

import sqlite3

from fitstat.config import ClientConfig
from fitstat.money import to_rubles


def _month_bounds(month: str) -> tuple[str, str]:
    """'2026-05' -> ('2026-05-01', '2026-06-01')"""
    year, mon = map(int, month.split("-"))
    next_year, next_mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return f"{year:04d}-{mon:02d}-01", f"{next_year:04d}-{next_mon:02d}-01"


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    return conn.execute(sql, params).fetchone()[0] or 0


def club_monthly_report(conn: sqlite3.Connection, cfg: ClientConfig, club_id: int, month: str) -> dict:
    start, end = _month_bounds(month)
    period = (club_id, start, end)

    revenue = _scalar(
        conn,
        "SELECT SUM(amount_kop) FROM sales WHERE club_id = ? AND sale_date >= ? AND sale_date < ?",
        period,
    )
    revenue_own = _scalar(
        conn,
        "SELECT SUM(amount_kop) FROM sales"
        " WHERE club_id = ? AND sale_date >= ? AND sale_date < ? AND channel = 'own'",
        period,
    )
    visits = _scalar(
        conn,
        "SELECT COUNT(*) FROM visits WHERE club_id = ? AND visit_date >= ? AND visit_date < ?",
        period,
    )
    active_members = _scalar(
        conn,
        "SELECT COUNT(DISTINCT person_id) FROM visits"
        " WHERE club_id = ? AND visit_date >= ? AND visit_date < ? AND visit_type = 'regular'",
        period,
    )
    pt_sessions = _scalar(
        conn,
        "SELECT COUNT(*) FROM sessions WHERE club_id = ? AND session_date >= ? AND session_date < ?",
        period,
    )
    pt_revenue = _scalar(
        conn,
        "SELECT SUM(amount_kop) FROM sales"
        " WHERE club_id = ? AND sale_date >= ? AND sale_date < ? AND kind = 'personal_training'",
        period,
    )

    return {
        "club_id": club_id,
        "month": month,
        "revenue": to_rubles(revenue),
        "revenue_own": to_rubles(revenue_own),
        "visits": visits,
        "active_members": active_members,
        "pt_sessions": pt_sessions,
        "pt_revenue": to_rubles(pt_revenue),
    }


def trainer_monthly_report(conn: sqlite3.Connection, cfg: ClientConfig, trainer_id: int, month: str) -> dict:
    start, end = _month_bounds(month)
    period = (trainer_id, start, end)

    sessions = _scalar(
        conn,
        "SELECT COUNT(*) FROM sessions WHERE trainer_id = ? AND session_date >= ? AND session_date < ?",
        period,
    )
    pt_revenue = _scalar(
        conn,
        "SELECT SUM(s.amount_kop) FROM sessions ss JOIN sales s ON s.id = ss.sale_id"
        " WHERE ss.trainer_id = ? AND ss.session_date >= ? AND ss.session_date < ?",
        period,
    )

    return {
        "trainer_id": trainer_id,
        "month": month,
        "sessions": sessions,
        "pt_revenue": to_rubles(pt_revenue),
    }


def network_monthly_report(conn: sqlite3.Connection, cfg: ClientConfig, month: str) -> dict:
    """Итоги по сети. Клубы, закрытые к началу месяца (closed_since в конфиге), не учитываются."""
    start, _ = _month_bounds(month)
    club_ids = [row[0] for row in conn.execute("SELECT id FROM clubs ORDER BY id")]
    open_clubs = [
        club_id for club_id in club_ids
        if not (cfg.club(club_id).get("closed_since") and cfg.club(club_id)["closed_since"] <= start)
    ]

    totals = {"revenue": 0.0, "visits": 0, "pt_sessions": 0}
    for club_id in open_clubs:
        club = club_monthly_report(conn, cfg, club_id, month)
        for key in totals:
            totals[key] += club[key]

    return {
        "month": month,
        "clubs_count": len(open_clubs),
        "revenue": round(totals["revenue"], 2),
        "visits": totals["visits"],
        "pt_sessions": totals["pt_sessions"],
    }
