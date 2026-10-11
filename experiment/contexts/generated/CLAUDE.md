# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repo and docs are in Russian (fitness club chain reporting system). Respond to the user in Russian when they write in Russian.

## Commands

```bash
# Import a client's CRM export (raw/<client>/*.csv) into data/<client>.db
python -m fitstat import alpha

# Monthly reports (club / trainer / whole network)
python -m fitstat report alpha --club 7 --month 2026-05
python -m fitstat report alpha --trainer 12 --month 2026-05
python -m fitstat report alpha --month 2026-05

# Run all tests
python -m unittest discover -s tests

# Run a single test file / case / method
python -m unittest tests.test_reports
python -m unittest tests.test_reports.ClubReportTest
python -m unittest tests.test_reports.ClubReportTest.test_club_may
```

Requires Python 3.11+ (uses `tomllib`), no external dependencies. `data/` (built SQLite DBs) is gitignored and rebuilt via `import`.

## Architecture

Pipeline: `clients/<slug>.toml` (config) + `raw/<slug>/*.csv` (CRM export) → `fitstat.importer.import_client` → `data/<slug>.db` (SQLite) → `fitstat.reports.*` → JSON.

- **`fitstat/config.py`** — loads `clients/<slug>.toml` into a `ClientConfig`. `partner_channels` lists the client-specific raw channel values that count as `partner` (everything else normalizes to `own`). Per-club settings (e.g. `closed_since`) live under `[clubs.<id>]`.
- **`fitstat/db.py`** — the SQLite schema (`clubs`, `trainers`, `persons`, `visits`, `sales`, `sessions`). Money is stored as integer kopecks (`amount_kop`) everywhere in the DB; conversion to rubles happens only at report output time via `fitstat/money.py`.
- **`fitstat/importer.py`** — reads six CSVs per client from `raw/<slug>/`, normalizes `channel` to `own`/`partner` using the client's `partner_channels`, converts amounts to kopecks, and bulk-inserts into a fresh DB (existing DB file is deleted before each import — not incremental).
- **`fitstat/reports.py`** — the public interface: `club_monthly_report`, `trainer_monthly_report`, `network_monthly_report`. **Their signatures must not change** — client data exports depend on them. `network_monthly_report` sums per-club reports but excludes clubs whose `closed_since` (from the client config) is on/before the report month's start. Month strings are `YYYY-MM`; `_month_bounds` converts them to a half-open `[start, end)` date range used in all date comparisons.
- **`fitstat/money.py`** — kopeck arithmetic. `to_kopecks`/`to_rubles` convert at the system boundary; `split_evenly` distributes a kopeck total across N parts without losing remainder kopecks (extra kopecks go to the first parts).
- **`fitstat/cli.py`** — argparse entry point (`import` / `report` subcommands), wired via `fitstat/__main__.py`.

### Metrics semantics

`docs/metrics.md` is the authoritative, current definition of each metric (revenue vs. revenue_own, active_members cohort, trial visit types including `guest_pass` since 2025, trial_conversion window of 14 days, etc.) — read it before touching report calculations, since several definitions are not obvious from the SQL alone (e.g. `active_members` only counts `regular` visits, not trials).

`legacy/METRICS.md` and `legacy/report_v1.sql` describe the **old v1** report (different, simpler definitions, e.g. trial_conversion as a flat ratio with no cohort/window). They're historical reference only — do not use them as a spec for current behavior, and note that `trial_conversion` from v1 has no equivalent implemented in `fitstat/reports.py` yet.

### Tests

`tests/helpers.demo_db()` builds an in-memory DB from the fixture client `tests/fixtures/clients/demo.toml` + `tests/fixtures/raw/demo/*.csv`. Both report and importer tests assert against hand-computed values from this fixture — when changing fixture CSVs, update the expected values in `tests/test_importer.py` and `tests/test_reports.py` accordingly.
