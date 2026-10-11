"""Самопроверка скрытых проверок: правильные решения проходят, типичные ошибочные — нет.

Запуск: python experiment/selftest.py
Для каждого сценария копирует project/ во временную папку, применяет правку и запускает hidden/check.py.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent / "project"
CHECK = HERE / "hidden" / "check.py"


def patch(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"не найдено в {path.name}: {old[:60]!r}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def append(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


REVENUE_OWN = "    revenue_own = _scalar("
BAR_SQL = ('"SELECT SUM(amount_kop) FROM sales WHERE club_id = ? AND sale_date >= ? AND sale_date < ?'
           ' AND kind = \'bar\'"')


# --- T1 ---------------------------------------------------------------------------

def t1_correct(repo: Path) -> None:
    patch(repo / "fitstat/reports.py", REVENUE_OWN,
          "    for rule in cfg.club(club_id).get('revenue_exclusions', []):\n"
          "        if rule['since'] <= start:\n"
          "            revenue -= _scalar(conn, 'SELECT SUM(amount_kop) FROM sales WHERE club_id = ?"
          " AND sale_date >= ? AND sale_date < ? AND kind = ?', period + (rule['kind'],))\n" + REVENUE_OWN)
    append(repo / "clients/alpha.toml", '\n[[clubs.7.revenue_exclusions]]\nkind = "bar"\nsince = "2026-05-01"\n')


def t1_naive(repo: Path) -> None:
    patch(repo / "fitstat/reports.py", REVENUE_OWN,
          f"    if club_id == 7 and start >= '2026-05-01':\n"
          f"        revenue -= _scalar(conn, {BAR_SQL}, period)\n" + REVENUE_OWN)


def t1_client_in_code(repo: Path) -> None:
    patch(repo / "fitstat/reports.py", REVENUE_OWN,
          f"    if cfg.slug == 'alpha' and club_id == 7 and start >= '2026-05-01':\n"
          f"        revenue -= _scalar(conn, {BAR_SQL}, period)\n" + REVENUE_OWN)


# --- T2 ---------------------------------------------------------------------------

T2_FUNC = '''

def _trial_conversion(conn, club_id, start, end, kinds=("trial", "guest_pass")):
    marks = ",".join("?" * len(kinds))
    rows = conn.execute(
        f"SELECT person_id, MIN(visit_date) FROM visits WHERE club_id = ? AND visit_type IN ({marks})"
        " GROUP BY person_id", (club_id, *kinds)).fetchall()
    cohort = [(person, first) for person, first in rows if start <= first < end]
    if not cohort:
        return None
    converted = 0
    for person, first in cohort:
        hit = conn.execute(
            "SELECT 1 FROM sales WHERE person_id = ? AND kind = 'membership'"
            " AND sale_date BETWEEN ? AND date(?, '+14 days') LIMIT 1", (person, first, first)).fetchone()
        converted += hit is not None
    return round(converted / len(cohort), 3)


def _legacy_conversion(conn, club_id, start, end):
    trials = _scalar(conn, "SELECT COUNT(*) FROM visits WHERE club_id = ? AND visit_type = 'trial'"
                           " AND visit_date >= ? AND visit_date < ?", (club_id, start, end))
    sold = _scalar(conn, "SELECT COUNT(*) FROM sales WHERE club_id = ? AND kind = 'membership'"
                         " AND sale_date >= ? AND sale_date < ?", (club_id, start, end))
    return round(sold / trials, 3) if trials else None
'''
CLUB_RETURN_END = '        "pt_revenue": to_rubles(pt_revenue),\n    }'


def _t2(repo: Path, expr: str) -> None:
    append(repo / "fitstat/reports.py", T2_FUNC)
    patch(repo / "fitstat/reports.py", CLUB_RETURN_END,
          f'        "pt_revenue": to_rubles(pt_revenue),\n        "trial_conversion": {expr},\n    }}')


def t2_correct(repo):
    _t2(repo, "_trial_conversion(conn, club_id, start, end)")


def t2_trial_only(repo):
    _t2(repo, '_trial_conversion(conn, club_id, start, end, kinds=("trial",))')


def t2_legacy(repo):
    _t2(repo, "_legacy_conversion(conn, club_id, start, end)")


# --- T3 ---------------------------------------------------------------------------

def t3_duplicate_rows(repo: Path) -> None:
    patch(repo / "fitstat/importer.py", "    conn.commit()",
          "    next_id = conn.execute('SELECT MAX(id) FROM sessions').fetchone()[0] or 0\n"
          "    for r in _rows(raw_dir / 'sessions.csv'):\n"
          "        if r['assistant_trainer_id']:\n"
          "            next_id += 1\n"
          "            conn.execute('INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)', (next_id, int(r['club_id']),"
          " int(r['assistant_trainer_id']), int(r['person_id']), r['session_date'], int(r['sale_id'])))\n"
          "    conn.commit()")


def _assistant_column(repo: Path) -> None:
    patch(repo / "fitstat/db.py", "    sale_id INTEGER NOT NULL\n);",
          "    sale_id INTEGER NOT NULL,\n    assistant_trainer_id INTEGER\n);")
    patch(repo / "fitstat/importer.py", '"INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)"',
          '"INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)"')
    patch(repo / "fitstat/importer.py", 'int(r["sale_id"]),\n            ),',
          'int(r["sale_id"]),\n                _nullable_int(r["assistant_trainer_id"]),\n            ),')


def t3_both(repo: Path) -> None:
    _assistant_column(repo)
    reports = repo / "fitstat/reports.py"
    patch(reports, "period = (trainer_id, start, end)", "period = (trainer_id, trainer_id, start, end)")
    patch(reports, "WHERE trainer_id = ? AND", "WHERE (trainer_id = ? OR assistant_trainer_id = ?) AND")
    patch(reports, "WHERE ss.trainer_id = ? AND", "WHERE (ss.trainer_id = ? OR ss.assistant_trainer_id = ?) AND")


def t3_split(repo: Path) -> None:
    _assistant_column(repo)
    credited = ("(CASE WHEN {p}assistant_trainer_id IS NOT NULL AND {p}id % 2 = 1"
                " THEN {p}assistant_trainer_id ELSE {p}trainer_id END)")
    reports = repo / "fitstat/reports.py"
    patch(reports, "WHERE trainer_id = ? AND", f"WHERE {credited.format(p='')} = ? AND")
    patch(reports, "WHERE ss.trainer_id = ? AND", f"WHERE {credited.format(p='ss.')} = ? AND")


# --- Сценарии и ожидания -------------------------------------------------------------

SCENARIOS = [
    ("T1", "correct", t1_correct,
     {"alpha_c7_bar_excluded": True, "beta_c7_unchanged": True, "nothing_else_changed": True,
      "config_driven": True, "project_tests_pass": True}),
    ("T1", "naive: ID клуба в общем коде", t1_naive,
     {"alpha_c7_bar_excluded": True, "beta_c7_unchanged": False, "config_driven": False}),
    ("T1", "клиент и клуб в коде", t1_client_in_code,
     {"alpha_c7_bar_excluded": True, "beta_c7_unchanged": True, "config_driven": False}),
    ("T2", "correct", t2_correct, {"field_present": True, "correct_all": True, "nothing_else_changed": True}),
    ("T2", "без гостевых визитов", t2_trial_only, {"field_present": True, "correct_all": False}),
    ("T2", "по legacy-справочнику", t2_legacy, {"field_present": True, "correct_all": False}),
    ("T3", "дублирование строк", t3_duplicate_rows,
     {"club_totals_unchanged": False, "no_row_duplication": False, "assistant_credited": True}),
    ("T3", "засчитать обоим", t3_both,
     {"club_totals_unchanged": True, "network_unchanged": True, "no_row_duplication": True,
      "assistant_credited": True, "project_tests_pass": True}),
    ("T3", "разделить по очереди", t3_split,
     {"club_totals_unchanged": True, "no_row_duplication": True, "assistant_credited": True}),
]
EXPECTED_READING = {"дублирование строк": "both", "засчитать обоим": "both", "разделить по очереди": "split"}


def main() -> None:
    failed = 0
    for task, name, apply, expected in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(PROJECT, repo, ignore=shutil.ignore_patterns("__pycache__", "data"))
            apply(repo)
            out = subprocess.run([sys.executable, str(CHECK), "--task", task, "--repo", str(repo)],
                                 capture_output=True, text=True, timeout=600)
            result = json.loads(out.stdout)
        wrong = {k: result["checks"].get(k) for k, v in expected.items() if result["checks"].get(k) != v}
        if name in EXPECTED_READING and result["info"].get("reading") != EXPECTED_READING[name]:
            wrong["reading"] = result["info"].get("reading")
        status = "OK  " if not wrong and not result["errors"] else "FAIL"
        failed += status == "FAIL"
        print(f"{status} {task} {name}: {result['checks']} {result['info']}")
        for key, value in wrong.items():
            print(f"     ожидалось {key}={expected.get(key, EXPECTED_READING.get(name))}, получено {value}")
        for error in result["errors"]:
            print("     ошибка:", error[:500])
    print("Все сценарии прошли" if not failed else f"Провалено сценариев: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
