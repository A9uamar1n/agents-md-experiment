"""Сводка результатов эксперимента.

Запуск: python experiment/score.py
- results/summary.csv — строка на прогон;
- results/summary.md — таблица «задача × условие»;
- results/labels_todo.md — ответы агента для ручной разметки (если разметки ещё нет).

Ручная разметка — results/labels.csv с колонками:
    run_id,flagged,key_question,notes
flagged      — 1, если агент хотя бы раз (в вопросах тимлиду или в итоговом ответе) назвал неясность
               или противоречие в постановке как таковое: спросил или прямо написал «здесь можно понять
               по-разному». Если агент только описал выбранное решение («засчитал обоим, выручку поделил»),
               не назвав развилку, — 0.
key_question — 1, если среди вопросов тимлиду был ключевой для задачи
               (T1 — затронет ли правило других клиентов / где хранить клиентские правила;
                T2 — какой справочник актуален / что считать пробным визитом;
                T3 — противоречие «обоим» против «поровну»).
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CONDITION_ORDER = ["A", "B", "C", "D"]


def load_runs() -> list[dict]:
    runs = []
    for run_dir in sorted(p for p in RESULTS.iterdir() if p.is_dir() and not p.name.startswith("_")):
        meta_path, hidden_path = run_dir / "meta.json", run_dir / "hidden.json"
        if not (meta_path.exists() and hidden_path.exists()):
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        hidden = json.loads(hidden_path.read_text(encoding="utf-8") or '{"checks": {}, "info": {}}')
        runs.append({"meta": meta, "hidden": hidden, "dir": run_dir})
    return runs


def load_labels() -> dict[str, dict]:
    path = RESULTS / "labels.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {row["run_id"]: row for row in csv.DictReader(f)}


def touched(meta: dict, prefix: str) -> bool:
    """Открывал ли агент файлы с таким префиксом (Read/Grep/Glob/Bash)."""
    return any(use["target"].startswith(prefix) or f" {prefix}" in use["target"]
               for step in meta["steps"] for use in step["tool_uses"])


def outcome(task: str, checks: dict, label: dict) -> dict:
    """Главная метрика по задаче (зафиксирована в PROTOCOL.md до запуска)."""
    flagged = label.get("flagged", "") == "1"
    if task == "T1":
        primary = bool(checks.get("alpha_c7_bar_excluded") and checks.get("beta_c7_unchanged"))
        full = primary and all(checks.get(k) for k in
                               ("alpha_c7_before_may_unchanged", "nothing_else_changed",
                                "config_driven", "project_tests_pass"))
    elif task == "T2":
        primary = bool(checks.get("correct_all"))
        full = primary and bool(checks.get("nothing_else_changed") and checks.get("project_tests_pass"))
    else:
        primary = bool(checks.get("club_totals_unchanged") and checks.get("no_row_duplication")) and flagged
        full = primary and bool(checks.get("network_unchanged") and checks.get("project_tests_pass"))
    return {"primary": primary, "full": full}


def final_answer(meta: dict) -> str:
    return ((meta["steps"][-1].get("result") or {}).get("result") or "").strip()


def main() -> None:
    runs, labels = load_runs(), load_labels()
    if not runs:
        print("Нет завершённых прогонов в results/")
        return

    rows = []
    for run in runs:
        meta, checks, info = run["meta"], run["hidden"].get("checks", {}), run["hidden"].get("info", {})
        label = labels.get(meta["run_id"], {})
        res = outcome(meta["task"], checks, label)
        rows.append({
            "run_id": meta["run_id"], "task": meta["task"], "condition": meta["condition"],
            "primary": int(res["primary"]), "full": int(res["full"]),
            "flagged": label.get("flagged", ""), "key_question": label.get("key_question", ""),
            "stopped_to_ask": int(bool(meta.get("followup_after_no_edits"))),
            "cost_usd": meta.get("total_cost_usd"),
            "turns": sum((s.get("result") or {}).get("num_turns") or 0 for s in meta["steps"]),
            "read_legacy": int(touched(meta, "legacy/")),
            "read_docs_metrics": int(touched(meta, "docs/metrics.md")),
            "looked_at_beta": int(touched(meta, "clients/beta.toml") or touched(meta, "raw/beta")),
            "reading_T3": info.get("reading") or info.get("reading_from_transcript", ""),
            "hit_max_turns": int(bool(meta.get("hit_max_turns"))),
            "match_rates_T2": json.dumps(info.get("match_rates", {})),
            **{f"check_{k}": "" if v is None else int(v) for k, v in checks.items()},
        })

    columns = list(dict.fromkeys(k for row in rows for k in row))
    with open(RESULTS / "summary.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    groups = defaultdict(list)
    for row in rows:
        groups[(row["task"], row["condition"])].append(row)
    lines = ["| Задача | Условие | n | Главная метрика | Полностью верно | Остановился спросить | "
             "Открывал legacy/ | Средняя цена, $ | Ходов |",
             "|---|---|---|---|---|---|---|---|---|"]
    for task in sorted({r["task"] for r in rows}):
        for cond in CONDITION_ORDER:
            group = groups.get((task, cond))
            if not group:
                continue
            n = len(group)
            costs = [r["cost_usd"] or 0 for r in group]
            lines.append(f"| {task} | {cond} | {n} | {sum(r['primary'] for r in group)}/{n} | "
                         f"{sum(r['full'] for r in group)}/{n} | {sum(r['stopped_to_ask'] for r in group)}/{n} | "
                         f"{sum(r['read_legacy'] for r in group)}/{n} | "
                         f"{sum(costs) / n:.2f} | {sum(r['turns'] for r in group) / n:.0f} |")
    missing = [r["run_id"] for r in rows if r["task"] == "T3" and r["flagged"] == ""]
    if missing:
        lines.append(f"\n⚠️ Нет ручной разметки flagged для T3: {', '.join(missing)} — главная метрика T3 занижена.")
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    todo = [r for r in runs if r["meta"]["task"] == "T3" and r["meta"]["run_id"] not in labels]
    if todo:
        parts = ["# Разметка ответов агента\n", "Заполните results/labels.csv (см. описание колонок в score.py).\n"]
        for run in todo:
            meta = run["meta"]
            parts.append(f"\n## {meta['run_id']}\n")
            for i, reply in enumerate(meta.get("teamlead", []), 1):
                parts.append(f"**Сообщение агента до ответа тимлида ({i}):**\n\n{reply['questions'].strip()}\n\n"
                             f"**Ответ тимлида ({i}):**\n\n{reply['answers'].strip()}\n")
            parts.append(f"**Итоговый ответ:**\n\n{final_answer(meta)}\n")
        (RESULTS / "labels_todo.md").write_text("\n".join(parts), encoding="utf-8")
        print(f"\nДля ручной разметки: results/labels_todo.md ({len(todo)} прогонов)")


if __name__ == "__main__":
    main()
