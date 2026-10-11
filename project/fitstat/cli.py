"""Командная строка: python -m fitstat import|report ..."""
import argparse
import json

from fitstat import reports
from fitstat.config import ROOT, load_config
from fitstat.db import connect
from fitstat.importer import import_client

DATA_DIR = ROOT / "data"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fitstat")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="загрузить выгрузку клиента в data/<client>.db")
    p_import.add_argument("client")

    p_report = sub.add_parser("report", help="ежемесячный отчёт по клубу, тренеру или сети")
    p_report.add_argument("client")
    p_report.add_argument("--month", required=True, help="YYYY-MM")
    target = p_report.add_mutually_exclusive_group()
    target.add_argument("--club", type=int)
    target.add_argument("--trainer", type=int)

    args = parser.parse_args(argv)
    cfg = load_config(args.client)
    db_path = DATA_DIR / f"{args.client}.db"

    if args.command == "import":
        DATA_DIR.mkdir(exist_ok=True)
        db_path.unlink(missing_ok=True)
        counts = import_client(connect(db_path), cfg)
        print(json.dumps(counts, ensure_ascii=False))
        return

    if not db_path.exists():
        parser.error(f"нет базы {db_path}; сначала выполните: python -m fitstat import {args.client}")
    conn = connect(db_path)
    if args.club is not None:
        result = reports.club_monthly_report(conn, cfg, args.club, args.month)
    elif args.trainer is not None:
        result = reports.trainer_monthly_report(conn, cfg, args.trainer, args.month)
    else:
        result = reports.network_monthly_report(conn, cfg, args.month)
    print(json.dumps(result, ensure_ascii=False, indent=2))
