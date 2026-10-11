"""Генератор синтетических выгрузок для демо-проекта fitstat.

Данные детерминированы (фиксированный seed), поэтому эксперимент можно повторить.
Запуск: python experiment/gen_data.py  -> перезаписывает project/raw/<client>/*.csv

Что специально заложено в данные (см. PROTOCOL.md):
- у обоих клиентов есть клуб №7 (ID локальны для каждого клиента);
- в клубе №7 обоих клиентов есть продажи бара;
- пробные визиты двух типов (trial и guest_pass), часть покупок абонемента позже 14 дней;
- часть персональных тренировок проведена вдвоём (assistant_trainer_id).
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "project" / "raw"

START = date(2026, 1, 1)
END = date(2026, 6, 30)

CLIENTS = {
    "alpha": {
        "seed": 11,
        "brand": "Альфа",
        "clubs": 8,
        "own_channel": "own",
        "partner_channels": ["sportpass", "fitmost"],
        "closed": {3: date(2026, 4, 1)},
    },
    "beta": {
        "seed": 22,
        "brand": "Бета",
        "clubs": 9,
        "own_channel": "direct",
        "partner_channels": ["sportpass", "gymbox"],
        "closed": {5: date(2026, 6, 1)},
    },
}

STREETS = ["Центр", "Ленина", "Парк", "Север", "Юг", "Набережная", "Заречье", "Вокзал", "Сити"]
FIRST_NAMES = ["Анна", "Иван", "Мария", "Олег", "Дарья", "Павел", "Елена", "Сергей", "Ольга", "Артём"]
LAST_NAMES = ["Смирнов", "Козлов", "Попов", "Волков", "Зайцев", "Соколов", "Морозов", "Орлов"]


def month_starts():
    d = START
    while d <= END:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def month_days(month_start: date, last_day: date) -> list[date]:
    next_month = date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1)
    end = min(next_month - timedelta(days=1), last_day)
    return [month_start + timedelta(days=i) for i in range((end - month_start).days + 1)]


def gen_client(slug: str, p: dict) -> dict[str, list[list]]:
    rnd = random.Random(p["seed"])
    counters = {"trainer": 0, "person": 0, "visit": 0, "sale": 0, "session": 0}

    def next_id(kind: str) -> int:
        counters[kind] += 1
        return counters[kind]

    def channel() -> str:
        return p["own_channel"] if rnd.random() < 0.75 else rnd.choice(p["partner_channels"])

    def amount(lo: int, hi: int, step: int) -> str:
        kopecks = rnd.choice(["00", "00", "50"])
        return f"{rnd.randrange(lo, hi, step)}.{kopecks}"

    rows = {name: [] for name in ["clubs", "trainers", "persons", "visits", "sales", "sessions"]}

    for club_id in range(1, p["clubs"] + 1):
        last_day = p["closed"].get(club_id, END + timedelta(days=1)) - timedelta(days=1)
        opened = date(rnd.randint(2018, 2024), rnd.randint(1, 12), rnd.randint(1, 28))
        rows["clubs"].append([club_id, f"{p['brand']} {STREETS[(club_id - 1) % len(STREETS)]}", opened.isoformat()])

        club_trainers = []
        for _ in range(rnd.randint(3, 5)):
            trainer_id = next_id("trainer")
            club_trainers.append(trainer_id)
            rows["trainers"].append([trainer_id, club_id, f"{rnd.choice(FIRST_NAMES)} {rnd.choice(LAST_NAMES)}"])

        members = []
        for _ in range(rnd.randint(30, 45)):
            person_id = next_id("person")
            created = date(2023, 1, 1) + timedelta(days=rnd.randint(0, 1094))
            rows["persons"].append([person_id, club_id, created.isoformat()])
            members.append(person_id)

        for month_start in month_starts():
            if month_start > last_day:
                break
            days = month_days(month_start, last_day)
            converted = []

            # Постоянные участники: обычные визиты и продления абонементов
            for person_id in members:
                if rnd.random() < 0.85:
                    for _ in range(rnd.randint(2, 10)):
                        rows["visits"].append([next_id("visit"), person_id, club_id, rnd.choice(days).isoformat(), "regular"])
                if rnd.random() < 0.45:
                    rows["sales"].append([next_id("sale"), club_id, person_id, rnd.choice(days).isoformat(),
                                          "membership", amount(2500, 6000, 100), channel()])

            # Новые люди: пробные и гостевые визиты, часть покупает абонемент
            for _ in range(rnd.randint(6, 16)):
                person_id = next_id("person")
                first = rnd.choice(days)
                rows["persons"].append([person_id, club_id, first.isoformat()])
                visit_type = "trial" if rnd.random() < 0.65 else "guest_pass"
                rows["visits"].append([next_id("visit"), person_id, club_id, first.isoformat(), visit_type])
                second = first + timedelta(days=rnd.randint(1, 7))
                if rnd.random() < 0.3 and second <= last_day:
                    rows["visits"].append([next_id("visit"), person_id, club_id, second.isoformat(), "trial"])
                if rnd.random() < 0.4:
                    bought = first + timedelta(days=rnd.randint(0, 25))
                    if bought <= min(last_day, END):
                        rows["sales"].append([next_id("sale"), club_id, person_id, bought.isoformat(),
                                              "membership", amount(2500, 6000, 100), channel()])
                        converted.append(person_id)

            # Бар: покупатель неизвестен, продажи только через собственный канал
            for _ in range(rnd.randint(25, 60)):
                rows["sales"].append([next_id("sale"), club_id, "", rnd.choice(days).isoformat(),
                                      "bar", amount(150, 900, 10), p["own_channel"]])

            # Персональные тренировки: одна оплата — одна тренировка, часть проведена вдвоём
            for trainer_id in club_trainers:
                for _ in range(rnd.randint(4, 14)):
                    day = rnd.choice(days).isoformat()
                    person_id = rnd.choice(members)
                    sale_id = next_id("sale")
                    rows["sales"].append([sale_id, club_id, person_id, day,
                                          "personal_training", amount(1800, 3500, 100), channel()])
                    assistant = ""
                    if rnd.random() < 0.12:
                        assistant = rnd.choice([t for t in club_trainers if t != trainer_id])
                    rows["sessions"].append([next_id("session"), club_id, trainer_id, person_id, day, sale_id, assistant])

            members.extend(converted)

    return rows


HEADERS = {
    "clubs": ["id", "name", "opened_at"],
    "trainers": ["id", "club_id", "name"],
    "persons": ["id", "club_id", "created_at"],
    "visits": ["id", "person_id", "club_id", "visit_date", "visit_type"],
    "sales": ["id", "club_id", "person_id", "sale_date", "kind", "amount", "channel"],
    "sessions": ["id", "club_id", "trainer_id", "person_id", "session_date", "sale_id", "assistant_trainer_id"],
}


def main() -> None:
    for slug, params in CLIENTS.items():
        out = RAW / slug
        out.mkdir(parents=True, exist_ok=True)
        for name, rows in gen_client(slug, params).items():
            with open(out / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(HEADERS[name])
                writer.writerows(rows)
            print(f"{slug}/{name}.csv: {len(rows)} строк")


if __name__ == "__main__":
    main()
