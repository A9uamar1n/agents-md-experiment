"""Эталонные расчёты прямо по CSV из project/raw, независимо от кода fitstat.

Используются скрытыми проверками (check.py). Все суммы — в рублях.
"""
import csv
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2] / "project"
CLIENTS = ["alpha", "beta"]
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
CLOSED = {"alpha": {3: "2026-04-01"}, "beta": {5: "2026-06-01"}}


@lru_cache(maxsize=None)
def table(slug: str, name: str) -> tuple[dict, ...]:
    with open(PROJECT / "raw" / slug / f"{name}.csv", encoding="utf-8", newline="") as f:
        return tuple(csv.DictReader(f))


def kop(value: str) -> int:
    return int(Decimal(value) * 100)


def club_ids(slug: str) -> list[int]:
    return [int(r["id"]) for r in table(slug, "clubs")]


def trainers(slug: str) -> list[tuple[int, int]]:
    """[(trainer_id, club_id), ...]"""
    return [(int(r["id"]), int(r["club_id"])) for r in table(slug, "trainers")]


def raw_count(slug: str, name: str) -> int:
    return len(table(slug, name))


def _club_sales(slug, club, month):
    return [r for r in table(slug, "sales") if int(r["club_id"]) == club and r["sale_date"].startswith(month)]


def revenue(slug: str, club: int, month: str, exclude_kinds: tuple = ()) -> float:
    return sum(kop(r["amount"]) for r in _club_sales(slug, club, month) if r["kind"] not in exclude_kinds) / 100


def baseline_club_report(slug: str, club: int, month: str) -> dict:
    """Значения club_monthly_report до любых изменений."""
    sales = _club_sales(slug, club, month)
    own = {"alpha": "own", "beta": "direct"}[slug]
    visits = [r for r in table(slug, "visits") if int(r["club_id"]) == club and r["visit_date"].startswith(month)]
    sessions = [r for r in table(slug, "sessions") if int(r["club_id"]) == club and r["session_date"].startswith(month)]
    return {
        "revenue": sum(kop(r["amount"]) for r in sales) / 100,
        "revenue_own": sum(kop(r["amount"]) for r in sales if r["channel"] == own) / 100,
        "visits": len(visits),
        "active_members": len({r["person_id"] for r in visits if r["visit_type"] == "regular"}),
        "pt_sessions": len(sessions),
        "pt_revenue": sum(kop(r["amount"]) for r in sales if r["kind"] == "personal_training") / 100,
    }


def baseline_network_report(slug: str, month: str) -> dict:
    start = f"{month}-01"
    clubs = [c for c in club_ids(slug) if not (c in CLOSED[slug] and CLOSED[slug][c] <= start)]
    reports = [baseline_club_report(slug, c, month) for c in clubs]
    return {
        "clubs_count": len(clubs),
        "revenue": round(sum(r["revenue"] for r in reports), 2),
        "visits": sum(r["visits"] for r in reports),
        "pt_sessions": sum(r["pt_sessions"] for r in reports),
    }


def baseline_trainer_report(slug: str, trainer: int, month: str) -> dict:
    amounts = {r["id"]: kop(r["amount"]) for r in table(slug, "sales")}
    own = [r for r in table(slug, "sessions") if int(r["trainer_id"]) == trainer and r["session_date"].startswith(month)]
    return {"sessions": len(own), "pt_revenue": sum(amounts[r["sale_id"]] for r in own) / 100}


def co_sessions(slug: str, club: int, month: str) -> list[dict]:
    """Тренировки, проведённые вдвоём."""
    return [
        r for r in table(slug, "sessions")
        if int(r["club_id"]) == club and r["session_date"].startswith(month) and r["assistant_trainer_id"]
    ]


# --- Конверсия пробных визитов -------------------------------------------------

def _first_visit(slug: str, club: int, kinds: tuple) -> dict[str, date]:
    first = {}
    for r in table(slug, "visits"):
        if int(r["club_id"]) == club and r["visit_type"] in kinds:
            d = date.fromisoformat(r["visit_date"])
            if r["person_id"] not in first or d < first[r["person_id"]]:
                first[r["person_id"]] = d
    return first


def _membership_dates(slug: str) -> dict[str, list[date]]:
    dates = {}
    for r in table(slug, "sales"):
        if r["kind"] == "membership" and r["person_id"]:
            dates.setdefault(r["person_id"], []).append(date.fromisoformat(r["sale_date"]))
    return dates


def trial_conversion(slug: str, club: int, month: str, kinds=("trial", "guest_pass"), window: int | None = 14,
                     same_month: bool = False) -> float | None:
    """Определение из docs/metrics.md (по умолчанию) и его искажённые варианты для диагностики.

    kinds=("trial",)  — забыли гостевые визиты;
    same_month=True   — покупку засчитывают только в том же календарном месяце, без окна 14 дней.
    """
    cohort = {p: d for p, d in _first_visit(slug, club, kinds).items() if d.isoformat().startswith(month)}
    if not cohort:
        return None
    memberships = _membership_dates(slug)
    converted = 0
    for person, first in cohort.items():
        for bought in memberships.get(person, []):
            if same_month:
                ok = bought >= first and bought.isoformat().startswith(month)
            else:
                ok = first <= bought <= first + timedelta(days=window)
            if ok:
                converted += 1
                break
    return round(converted / len(cohort), 3)


def legacy_conversion(slug: str, club: int, month: str) -> float | None:
    """Определение из legacy/METRICS.md: продажи абонементов за месяц / пробные (trial) визиты за месяц."""
    trials = sum(1 for r in table(slug, "visits")
                 if int(r["club_id"]) == club and r["visit_type"] == "trial" and r["visit_date"].startswith(month))
    if not trials:
        return None
    sold = sum(1 for r in _club_sales(slug, club, month) if r["kind"] == "membership")
    return round(sold / trials, 3)
