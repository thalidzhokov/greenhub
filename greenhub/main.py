"""Генератор коммитов для таймлайна GitHub. Использование: main.py <путь к репо>."""

import json
import os
import random
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

from font import load_font, render_text
from snippets import LANGUAGES

GLYPHS_PATH = Path(__file__).resolve().parent.parent / "glyphs.txt"
MAX_WEEKS = 52  # ширина таймлайна
# GitHub индексирует для графа контрибуций не более ~1000 коммитов за один пуш,
# лишние теряются безвозвратно — пушим партиями с запасом
PUSH_BATCH = 500


def get_env(name: str) -> str:
    return os.environ.get(name, "").strip().strip("\"'")


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def git(repo: str, *args: str, extra_env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(extra_env or {})},
    )
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def configure_git_user(repo: str, token: str) -> None:
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
    print(f"Автор коммитов: {name} <{email}>")


def text_targets(text: str, start: date, commits_per_cell: int) -> dict[date, int]:
    """Накладывает маску текста на календарь, начиная с недели даты start."""
    # вперёд к ближайшему воскресенью (началу колонки таймлайна)
    week_start = start + timedelta(days=(7 - (start.weekday() + 1) % 7) % 7)
    columns = render_text(text, load_font(GLYPHS_PATH))
    if len(columns) > MAX_WEEKS:
        print(f"Текст шире {MAX_WEEKS} недель ({len(columns)}), лишнее обрезано")
        columns = columns[:MAX_WEEKS]
    return {
        week_start + timedelta(weeks=week, days=day): commits_per_cell
        for week, column in enumerate(columns)
        for day, filled in enumerate(column)
        if filled
    }


def random_targets(start: date, end: date, low: int, high: int) -> dict[date, int]:
    return {
        start + timedelta(days=i): random.randint(low, high)
        for i in range((end - start).days + 1)
    }


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


def main() -> None:
    repo = sys.argv[1]

    langs = [
        lang
        for lang in re.split(r"[,\s]+", get_env("GH_LANGUAGES").lower())
        if lang
    ]
    unknown = sorted(set(langs) - set(LANGUAGES))
    if unknown:
        print(f"Неизвестные языки пропущены: {', '.join(unknown)}")
        langs = [lang for lang in langs if lang in LANGUAGES]
    if not langs:
        sys.exit(f"GH_LANGUAGES пуст; доступны: {', '.join(sorted(LANGUAGES))}")

    max_commits = int(get_env("GH_MAX_DAILY_COMMITS") or 1)
    start = parse_date(get_env("GH_START_DATE"))
    text = get_env("GH_TEXT")

    if text:
        targets = text_targets(text, start, max_commits)
    else:
        min_commits = int(get_env("GH_MIN_DAILY_COMMITS") or 1)
        end = parse_date(get_env("GH_END_DATE"))
        targets = random_targets(start, end, min_commits, max_commits)

    today = date.today()
    targets = {day: count for day, count in targets.items() if day <= today}

    configure_git_user(repo, get_env("GH_TOKEN"))
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
                unpushed = 0
        created += need
        print(f"{day}: +{need} коммитов")

    if unpushed:
        git(repo, "push", "origin", "HEAD")
    if created:
        print(f"Готово: создано и отправлено {created} коммитов")
    else:
        print("Готово: новых коммитов не требуется")


if __name__ == "__main__":
    main()
