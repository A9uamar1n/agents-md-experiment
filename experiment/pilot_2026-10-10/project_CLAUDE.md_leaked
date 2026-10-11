# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

fitstat — ежемесячные отчёты для сетей фитнес-клубов: импорт выгрузок из CRM клиента и отчёты по клубам, тренерам и сети целиком. Python 3.11+, без внешних зависимостей.

## Commands

```bash
# Импорт выгрузки клиента (raw/<client>/*.csv) в data/<client>.db
python -m fitstat import alpha

# Отчёты
python -m fitstat report alpha --club 7 --month 2026-05
python -m fitstat report alpha --trainer 12 --month 2026-05
python -m fitstat report alpha --month 2026-05        # вся сеть

# Тесты
python -m unittest discover -s tests
python -m unittest tests.test_reports.ClubReportTest.test_club_may   # один тест
```

## Architecture

- `fitstat/config.py` — загружает `clients/<slug>.toml`: имя клиента, `partner_channels` (список значений колонки `channel` в выгрузке, которые считаются партнёрскими продажами, маппинг свой для каждого клиента), и настройки по клубам (`[clubs.N]`, в т.ч. `closed_since` для закрытых клубов).
- `fitstat/importer.py` — читает CSV из `raw/<client>/` и пишет в SQLite-базу по схеме `fitstat/db.py`. Нормализует `channel` (own/partner) через конфиг клиента и конвертирует суммы в копейки (`fitstat/money.py`). У выгрузки `sessions.csv` есть колонка `assistant_trainer_id`, которая пока не импортируется.
- `fitstat/db.py` — схема SQLite: `clubs`, `trainers`, `persons`, `visits`, `sales`, `sessions`. Деньги хранятся в копейках (`amount_kop`), в рубли переводятся только на выходе отчёта.
- `fitstat/reports.py` — публичный интерфейс: `club_monthly_report`, `trainer_monthly_report`, `network_monthly_report`. **Сигнатуры этих функций не менять** — на них завязаны выгрузки клиентам. `network_monthly_report` суммирует отчёты по клубам, исключая клубы, закрытые к началу месяца (`closed_since` в конфиге клиента).
- `fitstat/cli.py` — точка входа `python -m fitstat`.

Данные клиентов изолированы: своя папка в `raw/`, свой toml в `clients/`, своя база в `data/` (не попадает в git). Тестовый набор — `tests/fixtures/` (клиент `demo`), используется через `tests/helpers.py:demo_db()`.

## Domain rules (docs/metrics.md)

Справочник метрик — источник истины для бизнес-логики отчётов (`docs/metrics.md`), важные моменты:

- Месяц отчёта — календарный месяц по дате события (`sale_date`, `visit_date`, `session_date`).
- `revenue` — все продажи клуба за месяц, любой канал. `revenue_own` — то же, но только канал `own`.
- `active_members` — число разных людей с хотя бы одним визитом типа `regular` за месяц (не `trial`/`guest_pass`).
- Пробный визит — типы `trial` и `guest_pass` (гостевые визиты считаются пробными с 2025 года).
- `trial_conversion` — доля людей из когорты пробных визитов месяца M, купивших абонемент (`membership`, любой канал) в день первого пробного визита или в следующие 14 календарных дней. Если когорта пустая — `None`.

`legacy/METRICS.md` и `legacy/report_v1.sql` — устаревшая v1-документация/логика (например, старое определение конверсии как простого отношения продаж к визитам за месяц, без когорт). Не использовать как источник правил — ориентироваться на `docs/metrics.md`.
