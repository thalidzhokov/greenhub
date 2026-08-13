"""Ядро greenhub: планирование и создание коммитов для таймлайна GitHub."""

import json
import os
import random
import subprocess
import tempfile
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path

from font import load_font, render_text
from snippets import LANGUAGES

GLYPHS_PATH = Path(__file__).resolve().parent.parent / "glyphs.txt"
# GitHub индексирует для графа контрибуций не более ~1000 коммитов за один пуш,
# лишние теряются безвозвратно — пушим партиями с запасом
PUSH_BATCH = 500

Log = Callable[[str], None]


def _auth_url(url: str, token: str) -> str:
    return url.replace("https://", f"https://x-access-token:{token}@")


def git(repo: str, *args: str, extra_env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(extra_env or {})},
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def clone_repo(url: str, token: str, dest: str, log: Log) -> None:
    log(f"Клонируем {url}")
    # для пустого репозитория ветка по умолчанию должна быть main,
    # иначе коммиты уйдут в недефолтную ветку и не попадут на таймлайн
    subprocess.run(
        ["git", "config", "--global", "init.defaultBranch", "main"], check=True
    )
    result = subprocess.run(
        ["git", "clone", _auth_url(url, token), dest],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone: {result.stderr.strip()}")


def ls_remote(url: str, token: str) -> tuple[str | None, int]:
    """Возвращает (ветка по умолчанию, число веток). RuntimeError, если репо недоступен."""
    result = subprocess.run(
        ["git", "ls-remote", "--symref", _auth_url(url, token)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    branch = None
    heads = 0
    for line in result.stdout.splitlines():
        if line.startswith("ref:") and line.endswith("\tHEAD"):
            branch = line.split()[1].removeprefix("refs/heads/")
        elif "\trefs/heads/" in line:
            heads += 1
    return branch, heads


def run_clear(url: str, token: str, log: Log) -> None:
    """Заменяет историю ветки по умолчанию одним пустым коммитом (force push)."""
    branch, heads = ls_remote(url, token)
    if heads == 0:
        log("Репозиторий уже пуст")
        return
    if branch is None:
        raise RuntimeError("Не удалось определить ветку по умолчанию")
    with tempfile.TemporaryDirectory(prefix="greenhub-") as tmp:
        git(tmp, "init", "-q")
        # автор без привязки к аккаунту GitHub — пустой коммит
        # не должен рисовать клетку на таймлайне
        git(tmp, "config", "user.name", "greenhub")
        git(tmp, "config", "user.email", "greenhub@localhost")
        git(tmp, "commit", "-q", "--allow-empty", "-m", "Clear repository")
        git(tmp, "push", "-q", "--force", _auth_url(url, token), f"HEAD:refs/heads/{branch}")
    log(f"История ветки {branch} заменена одним пустым коммитом")
    log("Таймлайн GitHub пересчитается в течение нескольких минут")


def configure_git_user(repo: str, token: str, log: Log) -> None:
    """Ставит имя и noreply-email владельца токена, чтобы коммиты попадали на таймлайн."""
    already = subprocess.run(
        ["git", "-C", repo, "config", "user.email"], capture_output=True
    )
    if already.returncode == 0:
        return
    request = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request) as response:
        user = json.load(response)
    name = user.get("name") or user["login"]
    email = f"{user['id']}+{user['login']}@users.noreply.github.com"
    git(repo, "config", "user.name", name)
    git(repo, "config", "user.email", email)
    log(f"Автор коммитов: {name} <{email}>")


def text_targets(
    text: str, start: date, low: int, high: int, rnd: random.Random
) -> dict[date, int]:
    """Накладывает маску текста на календарь, начиная с недели даты start."""
    # вперёд к ближайшему воскресенью (началу колонки таймлайна)
    week_start = start + timedelta(days=(7 - (start.weekday() + 1) % 7) % 7)
    columns = render_text(text, load_font(GLYPHS_PATH))
    return {
        week_start + timedelta(weeks=week, days=day): rnd.randint(low, high)
        for week, column in enumerate(columns)
        for day, filled in enumerate(column)
        if filled
    }


def fill_targets(
    start: date, end: date, weekdays: set[int], low: int, high: int, rnd: random.Random
) -> dict[date, int]:
    """Случайное число коммитов (low..high) на каждый день диапазона из weekdays."""
    return {
        day: rnd.randint(low, high)
        for i in range((end - start).days + 1)
        if (day := start + timedelta(days=i)).weekday() in weekdays
    }


def cap_today(targets: dict[date, int]) -> dict[date, int]:
    """Отбрасывает даты в будущем — GitHub их всё равно не показывает."""
    today = date.today()
    return {day: count for day, count in targets.items() if day <= today}


def existing_commits(repo: str) -> Counter[date]:
    result = subprocess.run(
        ["git", "-C", repo, "log", "--pretty=%ad", "--date=short"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # в репозитории ещё нет коммитов
        return Counter()
    return Counter(date.fromisoformat(line) for line in result.stdout.split())


def file_counts(repo: str, langs: list[str]) -> dict[str, int]:
    """Сколько файлов каждого языка уже накоплено в целевом репо."""
    return {
        lang: len(list(Path(repo, LANGUAGES[lang][0]).glob(f"*.{LANGUAGES[lang][0]}")))
        for lang in langs
    }


def make_commit(repo: str, lang: str, day: date, index: int) -> None:
    ext, comment, code = LANGUAGES[lang]
    # префикс выравнивается до 2 символов ("# " и "//"), чтобы файлы всех
    # языков были байт-в-байт одного размера
    body = f"{code}\n{comment:2} seed: {random.getrandbits(64):016x}\n"
    filename = f"{ext}/{day.isoformat()}_{index + 1}.{ext}"
    Path(repo, ext).mkdir(exist_ok=True)
    Path(repo, filename).write_text(body, encoding="utf-8", newline="\n")
    stamp = (datetime.combine(day, time(12, 0)) + timedelta(minutes=index)).isoformat()
    git(repo, "add", "-A")
    git(
        repo,
        "commit",
        "-q",
        "-m",
        f"Add {filename}",
        extra_env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )


def run_push(
    repo_url: str,
    token: str,
    langs: list[str],
    targets: dict[date, int],
    log: Log,
) -> int:
    """Клонирует репо во временную папку, докоммичивает недостающее и пушит.

    Возвращает число созданных коммитов.
    """
    with tempfile.TemporaryDirectory(prefix="greenhub-") as tmp:
        repo = str(Path(tmp) / "repo")
        clone_repo(repo_url, token, repo, log)
        configure_git_user(repo, token, log)
        existing = existing_commits(repo)
        counts = file_counts(repo, langs)

        created = 0
        unpushed = 0
        for day in sorted(targets):
            need = targets[day] - existing[day]
            if need <= 0:
                continue
            for i in range(need):
                # наименее заполненный язык — чтобы веса языков оставались равными
                lang = min(langs, key=lambda l: (counts[l], random.random()))
                counts[lang] += 1
                make_commit(repo, lang, day, existing[day] + i)
                unpushed += 1
                if unpushed == PUSH_BATCH:
                    git(repo, "push", "origin", "HEAD")
                    log(f"Отправлена партия из {PUSH_BATCH} коммитов")
                    unpushed = 0
            created += need
            log(f"{day}: +{need} коммитов")

        if unpushed:
            git(repo, "push", "origin", "HEAD")
        if created:
            log(f"Готово: создано и отправлено {created} коммитов")
        else:
            log("Готово: новых коммитов не требуется")
        return created
