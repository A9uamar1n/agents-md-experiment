"""Прогоны эксперимента через Claude Code в неинтерактивном режиме (claude -p).

Нужен установленный CLI `claude` в PATH (проверка: `claude --version`).

Подготовка условия D (один раз; результат замораживается в contexts/generated/):
    python experiment/run.py prepare-d
Прогоны (уже выполненные пропускаются, поэтому прерванный запуск можно продолжить):
    python experiment/run.py run --tasks T1,T2,T3 --conditions A,B,C,D --repeats 3
Результаты: experiment/results/<run_id>/ (transcript*.jsonl, diff.patch, hidden.json, meta.json)

Каждый прогон идёт в отдельной копии project/ во временной папке, вне репозитория,
чтобы агент не мог увидеть скрытые проверки, тексты других задач и результаты.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent / "project"
TASKS = HERE / "tasks"
CONTEXTS = HERE / "contexts"
RESULTS = HERE / "results"
CHECK = HERE / "hidden" / "check.py"
SANDBOX_ROOT = Path(tempfile.gettempdir()) / "fitstat-runs"

MAX_TURNS = 40
TIMEOUT_S = 30 * 60
ALLOWED_TOOLS = ("Read,Edit,Write,Glob,Grep,"
                 "Bash(python:*),Bash(python3:*),Bash(git status:*),Bash(git diff:*),Bash(ls:*)")
# --setting-sources project: не подхватывать личные ~/.claude/CLAUDE.md и настройки пользователя.
# Флаги меняются между версиями CLI — сверьтесь с `claude --help` перед запуском.
COMMON_FLAGS = ["--output-format", "stream-json", "--verbose",
                "--permission-mode", "acceptEdits", "--setting-sources", "project"]
ENV_EXTRA = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}

SUFFIX = "\n\nКогда закончишь, коротко опиши, что сделал и какие решения принял."
STEP2 = "Ответы на твои вопросы:\n\n{answers}\n\nТеперь реализуй задачу." + SUFFIX
SIM_USER = """Ты — тимлид проекта fitstat. ИИ-ассистент, которому поручили задачу, прислал вопросы.
Ответь на них коротко, опираясь только на факты ниже.

Правила:
- Отвечай только на заданные вопросы, по порядку. Не сообщай фактов, о которых не спрашивали.
- Если ответа нет в фактах, напиши «на твоё усмотрение».
- Не используй инструменты, просто ответь текстом.

Задача, которую получил ассистент:
{task}

Факты (известны только тебе):
{facts}

Вопросы ассистента:
{questions}
"""
INIT_FALLBACK = (
    "Please analyze this codebase and create a CLAUDE.md file, which will be given to future instances "
    "of Claude Code to operate in this repository. Include the commands needed to build, lint and test, "
    "and the high-level architecture that requires reading multiple files to understand."
)

CONDITIONS = {
    "A": "без файла контекста",
    "B": "AGENTS.md, написанный человеком",
    "C": "AGENTS.md + задача по шаблону: сначала вопросы, потом код",
    "D": "файл контекста, сгенерированный /init",
}


# --- Вызов Claude Code -------------------------------------------------------------

def claude_bin() -> str:
    path = shutil.which("claude")
    if not path:
        sys.exit("Не найден CLI `claude` в PATH. Установите Claude Code и проверьте `claude --version`.")
    return path


def claude_version() -> str:
    out = subprocess.run([claude_bin(), "--version"], capture_output=True, text=True, encoding="utf-8")
    return out.stdout.strip()


def call_claude(prompt: str, cwd: Path, model: str, transcript: Path,
                resume: str | None = None, allowed: str | None = ALLOWED_TOOLS, max_turns: int = MAX_TURNS) -> dict:
    """Запускает claude -p (промпт через stdin) и возвращает сводку по шагу."""
    cmd = [claude_bin(), "-p", "--model", model, "--max-turns", str(max_turns), *COMMON_FLAGS]
    if allowed:
        cmd += ["--allowedTools", allowed]
    if resume:
        cmd += ["--resume", resume]
    env = {**os.environ, **ENV_EXTRA}
    proc = subprocess.run(cmd, input=prompt, cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
    transcript.write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        transcript.with_suffix(".stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return summarize(proc.stdout, cwd, proc.returncode)


def summarize(stream: str, cwd: Path, returncode: int) -> dict:
    summary = {"returncode": returncode, "tool_uses": [], "result": None}
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            summary["init"] = {k: event.get(k) for k in ("model", "claude_code_version", "tools", "permissionMode")}
        elif event.get("type") == "assistant":
            for item in event.get("message", {}).get("content", []):
                if item.get("type") == "tool_use":
                    summary["tool_uses"].append(compact_tool_use(item, cwd))
        elif event.get("type") == "result":
            summary["result"] = {k: event.get(k) for k in
                                 ("session_id", "is_error", "subtype", "num_turns", "duration_ms",
                                  "total_cost_usd", "result", "usage", "modelUsage")}
    return summary


def compact_tool_use(item: dict, cwd: Path) -> dict:
    data = item.get("input", {})
    target = data.get("file_path") or data.get("path") or data.get("pattern") or data.get("command") or ""
    try:
        target = str(Path(target).resolve().relative_to(cwd.resolve())).replace("\\", "/")
    except (ValueError, OSError):
        pass
    return {"tool": item.get("name"), "target": str(target)[:300]}


# --- Песочница ---------------------------------------------------------------------

def rmtree(path: Path) -> None:
    """Удаляет папку целиком, включая файлы «только для чтения» из .git (на Windows обычный rmtree на них падает)."""
    def make_writable(func, failed_path, _exc):
        os.chmod(failed_path, stat.S_IWRITE)
        func(failed_path)

    if path.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=make_writable)
        else:
            shutil.rmtree(path, onerror=make_writable)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=experiment", "-c", "user.email=experiment@example.com", *args],
                          cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True).stdout


CONTEXT_FILES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".claude", ".cursor", ".cursorrules")


def assert_clean_project() -> None:
    """В project/ не должно быть файлов контекста: иначе они попадут во все условия, включая A."""
    found = sorted({str(p.relative_to(PROJECT)) for name in CONTEXT_FILES for p in PROJECT.rglob(name)})
    if found:
        sys.exit(f"В project/ есть файлы контекста для ИИ: {found}. Уберите их — "
                 f"файлы контекста для условий лежат только в experiment/contexts/.")


def make_sandbox(run_id: str, condition: str) -> Path:
    assert_clean_project()
    repo = SANDBOX_ROOT / run_id / "repo"
    rmtree(repo.parent)
    shutil.copytree(PROJECT, repo, ignore=shutil.ignore_patterns("__pycache__", "data"))
    context_dir = {"B": "human", "C": "human", "D": "generated"}.get(condition)
    if context_dir:
        files = [f for f in (CONTEXTS / context_dir).iterdir() if f.is_file()]
        if not files:
            sys.exit(f"Пустая папка contexts/{context_dir}. Для условия D сначала выполните prepare-d.")
        for f in files:
            shutil.copy2(f, repo / f.name)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "baseline")
    return repo


# --- Один прогон ---------------------------------------------------------------------

class InfraError(Exception):
    """Технический сбой (сеть, авторизация, лимиты) — прогон не засчитывается и будет повторён."""


def checked(step: dict) -> dict:
    result = step.get("result")
    if result and result.get("subtype") == "error_max_turns":
        # Агент не уложился в лимит ходов — это результат прогона, а не технический сбой
        step["hit_max_turns"] = True
        return step
    if not result or result.get("is_error"):
        raise InfraError((result or {}).get("result") or f"нет итогового события, код {step.get('returncode')}")
    return step


def has_edits(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain").strip())


def ask_teamlead(task: str, questions: str, run_id: str, sim_model: str, transcript: Path) -> dict:
    """Симулированный тимлид отвечает на вопросы агента, зная только факты из tasks/<task>.facts.md."""
    sim_dir = SANDBOX_ROOT / run_id / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    sim = checked(call_claude(SIM_USER.format(task=(TASKS / f"{task}.md").read_text(encoding="utf-8"),
                                              facts=(TASKS / f"{task}.facts.md").read_text(encoding="utf-8"),
                                              questions=questions),
                              sim_dir, sim_model, transcript, allowed=None, max_turns=3))
    return {"model": sim_model, "questions": questions, "answers": sim["result"]["result"],
            "cost": sim["result"].get("total_cost_usd")}


def run_one(task: str, condition: str, repeat: int, model: str, sim_model: str, keep: bool) -> None:
    run_id = f"{task}-{condition}-{repeat:02d}"
    out = RESULTS / run_id
    if (out / "hidden.json").exists():
        print(f"{run_id}: уже есть, пропускаю")
        return
    out.mkdir(parents=True, exist_ok=True)
    print(f"{run_id}: {CONDITIONS[condition]} ...", flush=True)
    repo = make_sandbox(run_id, condition)
    meta = {"run_id": run_id, "task": task, "condition": condition, "repeat": repeat, "model": model,
            "claude_version": claude_version(), "started_at": now(), "steps": [], "teamlead": []}

    try:
        if condition == "C":
            # Шаг 1: только вопросы. Шаг 2: ответы тимлида и реализация в той же сессии
            step = checked(call_claude((TASKS / f"{task}.template.md").read_text(encoding="utf-8"),
                                       repo, model, out / "transcript1.jsonl"))
            meta["steps"].append(step)
            meta["edited_in_step1"] = has_edits(repo)
            reply = ask_teamlead(task, step["result"]["result"], run_id, sim_model, out / "teamlead1.jsonl")
            meta["teamlead"].append(reply)
            step = checked(call_claude(STEP2.format(answers=reply["answers"]), repo, model,
                                       out / "transcript2.jsonl", resume=step["result"]["session_id"]))
            meta["steps"].append(step)
        else:
            prompt = (TASKS / f"{task}.md").read_text(encoding="utf-8") + SUFFIX
            step = checked(call_claude(prompt, repo, model, out / "transcript1.jsonl"))
            meta["steps"].append(step)

        # Если агент закончил, ничего не изменив, — значит, он задал вопросы и ждёт ответа.
        # Во всех условиях тимлид отвечает один раз, и агент продолжает (изменение протокола после пилота)
        if not has_edits(repo) and not step.get("hit_max_turns"):
            n = len(meta["teamlead"]) + 1
            reply = ask_teamlead(task, step["result"]["result"], run_id, sim_model, out / f"teamlead{n}.jsonl")
            meta["teamlead"].append(reply)
            step = checked(call_claude(STEP2.format(answers=reply["answers"]), repo, model,
                                       out / f"transcript{len(meta['steps']) + 1}.jsonl",
                                       resume=step["result"]["session_id"]))
            meta["steps"].append(step)
            meta["followup_after_no_edits"] = True
    except InfraError as error:
        failed = RESULTS / "_failed" / f"{run_id}_{datetime.now():%Y%m%d-%H%M%S}"
        failed.parent.mkdir(parents=True, exist_ok=True)
        meta["infra_error"] = str(error)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.move(str(out), str(failed))
        rmtree(repo.parent)
        print(f"{run_id}: технический сбой ({error}). Прогон не засчитан, перенесён в {failed.relative_to(HERE)}; "
              f"повторится при следующем запуске.", flush=True)
        return

    git(repo, "add", "-A")
    (out / "diff.patch").write_text(git(repo, "diff", "--cached"), encoding="utf-8")
    check = subprocess.run([sys.executable, str(CHECK), "--task", task, "--repo", str(repo)],
                           capture_output=True, text=True, encoding="utf-8", timeout=900)
    meta["finished_at"] = now()
    meta["hit_max_turns"] = any(s.get("hit_max_turns") for s in meta["steps"])
    meta["total_cost_usd"] = round(sum((s["result"] or {}).get("total_cost_usd") or 0 for s in meta["steps"])
                                   + sum(t.get("cost") or 0 for t in meta["teamlead"]), 4)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "hidden.json").write_text(check.stdout, encoding="utf-8")
    if not keep:
        rmtree(repo.parent)
    checks = json.loads(check.stdout)["checks"] if check.stdout else {}
    print(f"{run_id}: готово, ${meta['total_cost_usd']}, проверки: {checks}", flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Подготовка условия D ------------------------------------------------------------

def prepare_d(model: str) -> None:
    target = CONTEXTS / "generated"
    if target.exists() and any(target.iterdir()):
        sys.exit("contexts/generated/ уже заполнена. Удалите её содержимое, если хотите сгенерировать заново.")
    target.mkdir(parents=True, exist_ok=True)
    repo = make_sandbox("prepare-d", "A")
    log = {"model": model, "claude_version": claude_version(), "created_at": now()}
    for method, prompt in (("/init", "/init"), ("fallback", INIT_FALLBACK)):
        step = call_claude(prompt, repo, model, target.parent / f"generated_{method.strip('/')}.jsonl")
        try:
            checked(step)
        except InfraError as error:
            rmtree(repo.parent)
            sys.exit(f"Технический сбой: {error}\nИсправьте причину (например, войдите заново: `claude`, затем /login) "
                     f"и запустите prepare-d ещё раз. Ничего не создавайте вручную в project/.")
        produced = [repo / name for name in ("CLAUDE.md", "AGENTS.md") if (repo / name).exists()]
        if produced:
            for f in produced:
                shutil.copy2(f, target / f.name)
            log["method"] = method
            log["init_init_event"] = step.get("init")
            break
    else:
        rmtree(repo.parent)
        sys.exit("Ни /init, ни запасной промпт не создали файл (см. contexts/generated_*.jsonl).")
    (CONTEXTS / "generated.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    rmtree(repo.parent)
    print(f"Готово: {[f.name for f in target.iterdir()]}, способ: {log['method']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_d = sub.add_parser("prepare-d")
    p_d.add_argument("--model", default="sonnet")
    p_run = sub.add_parser("run")
    p_run.add_argument("--tasks", default="T1,T2,T3")
    p_run.add_argument("--conditions", default="A,B,C,D")
    p_run.add_argument("--repeats", type=int, default=3)
    p_run.add_argument("--model", default="sonnet")
    p_run.add_argument("--sim-model", default="sonnet")
    p_run.add_argument("--keep", action="store_true", help="не удалять песочницы после прогона")
    args = parser.parse_args()

    if args.command == "prepare-d":
        prepare_d(args.model)
        return
    tasks, conditions = args.tasks.split(","), args.conditions.split(",")
    # Чередуем задачи и условия внутри каждого повтора, чтобы изменения на стороне модели
    # во время эксперимента не совпали с одним условием
    for repeat in range(1, args.repeats + 1):
        for task in tasks:
            for condition in conditions:
                run_one(task, condition, repeat, args.model, args.sim_model, args.keep)


if __name__ == "__main__":
    main()
