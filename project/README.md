# fitstat

Ежемесячные отчёты для сетей фитнес-клубов: импорт выгрузок из CRM клиента и отчёты по клубам, тренерам и сети целиком.

Нужен Python 3.11+. Внешних зависимостей нет.

## Быстрый старт

```bash
python -m fitstat import alpha
python -m fitstat report alpha --club 7 --month 2026-05
python -m fitstat report alpha --trainer 12 --month 2026-05
python -m fitstat report alpha --month 2026-05        # вся сеть
```

## Тесты

```bash
python -m unittest discover -s tests
```

## Структура

- `fitstat/` — код: конфигурация, импорт, отчёты.
- `clients/` — настройки клиентов.
- `raw/` — выгрузки из CRM клиентов.
- `data/` — базы после импорта (в git не попадают).
- `docs/` — документация.
- `legacy/` — отчёты v1.
- `tests/` — тесты на небольшом тестовом наборе данных.

Публичный интерфейс — функции `club_monthly_report`, `trainer_monthly_report`, `network_monthly_report` из `fitstat/reports.py`. На них завязаны выгрузки клиентам, поэтому их сигнатуры не меняем.
