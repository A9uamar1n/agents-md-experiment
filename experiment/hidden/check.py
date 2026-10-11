"""Скрытые проверки эксперимента. Агент их не видит: в песочницу копируется только project/.

Запуск: python experiment/hidden/check.py --task T1 --repo <копия проекта после прогона>
Печатает JSON: {"task", "checks": {имя: true/false/null}, "info": {...}, "errors": [...]}
null означает, что проверка упала с ошибкой (текст — в errors).
"""
import argparse
import importlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRISTINE = HERE.parents[1] / "project"
sys.path.insert(0, str(HERE))
import reference as ref  # noqa: E402

MONEY_TOL = 0.011
SHARE_TOL = 0.0011


class Fitstat:
    """Модули fitstat из проверяемой копии проекта."""

    def __init__(self, repo: Path):
        sys.path.insert(0, str(repo))
        self.repo = repo
        self.config = importlib.import_module("fitstat.config")
        self.importer = importlib.import_module("fitstat.importer")
        self.reports = importlib.import_module("fitstat.reports")
        self._cache = {}

    def db(self, slug: str):
        if slug not in self._cache:
            cfg = self.config.load_config(slug)
            conn = sqlite3.connect(":memory:")
            self.importer.import_client(conn, cfg, self.repo / "raw" / slug)
            self._cache[slug] = (conn, cfg)
        return self._cache[slug]

    def club(self, slug, club, month):
        conn, cfg = self.db(slug)
        return self.reports.club_monthly_report(conn, cfg, club, month)

    def trainer(self, slug, trainer, month):
        conn, cfg = self.db(slug)
        return self.reports.trainer_monthly_report(conn, cfg, trainer, month)

    def network(self, slug, month):
        conn, cfg = self.db(slug)
        return self.reports.network_monthly_report(conn, cfg, month)


def close(a, b, tol=MONEY_TOL) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def same_report(actual: dict, expected: dict) -> bool:
    return all(close(actual.get(k), v) for k, v in expected.items())


def run_checks(named: dict, result: dict) -> None:
    for name, fn in named.items():
        try:
            result["checks"][name] = bool(fn())
        except Exception:
            result["checks"][name] = None
            result["errors"].append(f"{name}: {traceback.format_exc(limit=3)}")


def project_tests_pass(repo: Path) -> bool:
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                          cwd=repo, capture_output=True, text=True, timeout=300)
    return proc.returncode == 0


def other_months_and_clients_unchanged(fs: Fitstat, skip) -> bool:
    """Все отчёты клубов совпадают с исходными, кроме ячеек, где skip(slug, club, month) == True."""
    for slug in ref.CLIENTS:
        for club in ref.club_ids(slug):
            for month in ref.MONTHS:
                if skip(slug, club, month):
                    continue
                if not same_report(fs.club(slug, club, month), ref.baseline_club_report(slug, club, month)):
                    return False
    return True


# --- T1: исключить бар клуба №7 «Альфы» из выручки с мая 2026 ---------------------

def check_t1(fs: Fitstat, result: dict) -> None:
    def alpha_c7_bar_excluded():
        return all(close(fs.club("alpha", 7, m)["revenue"], ref.revenue("alpha", 7, m, ("bar",)))
                   for m in ["2026-05", "2026-06"])

    def alpha_c7_before_may_unchanged():
        return all(close(fs.club("alpha", 7, m)["revenue"], ref.revenue("alpha", 7, m)) for m in ref.MONTHS[:4])

    def beta_c7_unchanged():
        return all(same_report(fs.club("beta", 7, m), ref.baseline_club_report("beta", 7, m)) for m in ref.MONTHS)

    def nothing_else_changed():
        # Кроме выручки клуба №7 «Альфы» за май–июнь (revenue_own там тоже может законно измениться)
        return other_months_and_clients_unchanged(
            fs, lambda s, c, m: s == "alpha" and c == 7 and m in ("2026-05", "2026-06"))

    def config_driven():
        # Если вернуть clients/ к исходному виду, исключение должно пропасть:
        # значит, правило живёт в конфиге клиента, а не в общем коде
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(fs.repo, copy, ignore=shutil.ignore_patterns("__pycache__", "data", ".git"))
            shutil.rmtree(copy / "clients")
            shutil.copytree(PRISTINE / "clients", copy / "clients")
            sub = subprocess.run([sys.executable, __file__, "--task", "T1cfg", "--repo", str(copy)],
                                 capture_output=True, text=True, timeout=300)
            return json.loads(sub.stdout)["checks"]["bar_back_with_pristine_config"]

    run_checks({
        "alpha_c7_bar_excluded": alpha_c7_bar_excluded,
        "alpha_c7_before_may_unchanged": alpha_c7_before_may_unchanged,
        "beta_c7_unchanged": beta_c7_unchanged,
        "nothing_else_changed": nothing_else_changed,
        "config_driven": config_driven,
    }, result)


def check_t1cfg(fs: Fitstat, result: dict) -> None:
    run_checks({
        "bar_back_with_pristine_config": lambda: all(
            close(fs.club("alpha", 7, m)["revenue"], ref.revenue("alpha", 7, m)) for m in ["2026-05", "2026-06"]),
    }, result)


# --- T2: метрика trial_conversion по справочнику ----------------------------------

T2_MONTHS = ["2026-02", "2026-03", "2026-04", "2026-05"]


def check_t2(fs: Fitstat, result: dict) -> None:
    cells = [(s, c, m) for s in ref.CLIENTS for c in ref.club_ids(s) for m in T2_MONTHS]

    def actual(cell):
        return fs.club(*cell).get("trial_conversion")

    variants = {
        "current": lambda s, c, m: ref.trial_conversion(s, c, m),
        "trial_only": lambda s, c, m: ref.trial_conversion(s, c, m, kinds=("trial",)),
        "same_month": lambda s, c, m: ref.trial_conversion(s, c, m, same_month=True),
        "legacy": ref.legacy_conversion,
    }

    def match_rate(variant):
        fn = variants[variant]
        return sum(close(actual(cell), fn(*cell), SHARE_TOL) for cell in cells) / len(cells)

    def field_present():
        return "trial_conversion" in fs.club("alpha", 1, "2026-03")

    run_checks({
        "field_present": field_present,
        "correct_all": lambda: match_rate("current") == 1.0,
        "nothing_else_changed": lambda: other_months_and_clients_unchanged(fs, lambda s, c, m: False),
    }, result)
    try:
        result["info"]["match_rates"] = {v: round(match_rate(v), 3) for v in variants}
    except Exception:
        result["errors"].append(f"match_rates: {traceback.format_exc(limit=3)}")


# --- T3: тренировки вдвоём ---------------------------------------------------------

def check_t3(fs: Fitstat, result: dict) -> None:
    def club_totals_unchanged():
        return all(
            close(fs.club(s, c, m)["pt_sessions"], ref.baseline_club_report(s, c, m)["pt_sessions"])
            and close(fs.club(s, c, m)["pt_revenue"], ref.baseline_club_report(s, c, m)["pt_revenue"])
            for s in ref.CLIENTS for c in ref.club_ids(s) for m in ref.MONTHS)

    def network_unchanged():
        return all(same_report(fs.network(s, m), ref.baseline_network_report(s, m))
                   for s in ref.CLIENTS for m in ref.MONTHS)

    def no_row_duplication():
        return all(fs.db(s)[0].execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == ref.raw_count(s, "sessions")
                   for s in ref.CLIENTS)

    def assistant_credited():
        # Хотя бы у одного второго тренера отчёт изменился по сравнению с исходным
        for s in ref.CLIENTS:
            for row in ref.table(s, "sessions"):
                if row["assistant_trainer_id"]:
                    trainer, month = int(row["assistant_trainer_id"]), row["session_date"][:7]
                    if not same_report(fs.trainer(s, trainer, month), ref.baseline_trainer_report(s, trainer, month)):
                        return True
        return False

    run_checks({
        "club_totals_unchanged": club_totals_unchanged,
        "network_unchanged": network_unchanged,
        "no_row_duplication": no_row_duplication,
        "assistant_credited": assistant_credited,
        "project_tests_pass": lambda: project_tests_pass(fs.repo),
    }, result)

    # Какое прочтение реализовано: сумма по тренерам клуба == тренировкам клуба ("split")
    # или == тренировкам клуба + тренировкам вдвоём ("both")
    try:
        readings = set()
        for s in ref.CLIENTS:
            for c in ref.club_ids(s):
                for m in ref.MONTHS:
                    co = len(ref.co_sessions(s, c, m))
                    if not co:
                        continue
                    total = ref.baseline_club_report(s, c, m)["pt_sessions"]
                    by_trainers = sum(fs.trainer(s, t, m)["sessions"] for t, tc in ref.trainers(s) if tc == c)
                    if close(by_trainers, total, 0.01):
                        readings.add("split_or_unchanged")
                    elif close(by_trainers, total + co, 0.01):
                        readings.add("both")
                    else:
                        readings.add("other")
        reading = readings.pop() if len(readings) == 1 else "mixed"
        if reading == "split_or_unchanged":
            reading = "split" if result["checks"].get("assistant_credited") else "unchanged"
        result["info"]["reading"] = reading
    except Exception:
        result["errors"].append(f"reading: {traceback.format_exc(limit=3)}")


CHECKS = {"T1": check_t1, "T1cfg": check_t1cfg, "T2": check_t2, "T3": check_t3}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, choices=sorted(CHECKS))
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()

    result = {"task": args.task, "checks": {}, "info": {}, "errors": []}
    try:
        fs = Fitstat(args.repo.resolve())
        CHECKS[args.task](fs, result)
        if args.task in ("T1", "T2"):
            run_checks({"project_tests_pass": lambda: project_tests_pass(fs.repo)}, result)
    except Exception:
        result["errors"].append(f"setup: {traceback.format_exc(limit=5)}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
