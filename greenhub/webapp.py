"""Веб-интерфейс greenhub отвечает за форму параметров, превью таймлайна и запуск пуша."""

import os
import random
import threading
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any, cast
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request

import achievements
import core
from font import FONTS_DIR, available_fonts, load_font, render_text
from snippets import LANGUAGES

app = Flask(__name__)

MAX_COMMITS = 99
MAX_TEXT_LEN = 1000
# токен вставляется в URL и уходит хосту репозитория
# разрешаем только github.com
ALLOWED_HOSTS = {
    "github.com",
    # "gitlab.com",
    # "codeberg.org",
    # "gitee.com",
}
FONTS = available_fonts()
DEFAULT_FONT = "5x7-dotmatrix"

JOBS: dict[str, dict[str, Any]] = {}


def to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_iso(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def repo_params(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    """Достаёт и проверяет URL репозитория и токен: (repo, token, ошибка)."""
    repo = str(payload.get("repo", "")).strip()
    token = str(payload.get("token", "")).strip()
    if not repo.startswith("https://"):
        return repo, token, "URL репозитория должен начинаться с https://"
    try:
        host = urlsplit(repo).hostname
    except ValueError:
        host = None
    if host not in ALLOWED_HOSTS:
        allowed = ", ".join(sorted(ALLOWED_HOSTS))
        return repo, token, f"Хост репозитория не поддерживается, разрешены: {allowed}"
    if not token:
        return repo, token, "Укажите токен"
    return repo, token, None


def scrub(message: str, token: str) -> str:
    """Убирает токен из сообщений git (он попадает в URL в stderr)."""
    return message.replace(token, "***") if token else message


def commit_range(payload: dict[str, Any]) -> tuple[tuple[int, int] | None, str | None]:
    """Число коммитов на день: ((низ, верх), None) или (None, ошибка)."""
    if payload.get("random", True):
        low = to_int(payload.get("min_commits", 1))
        high = to_int(payload.get("max_commits", 5))
        if low is None or high is None or not 1 <= low < high <= MAX_COMMITS:
            return None, f"Для случайного режима нужно: 1 ≤ от < до ≤ {MAX_COMMITS}"
        return (low, high), None
    commits = to_int(payload.get("commits", 1))
    if commits is None or not 1 <= commits <= MAX_COMMITS:
        return None, f"Число коммитов: от 1 до {MAX_COMMITS}"
    return (commits, commits), None


def start_date(payload: dict[str, Any]) -> tuple[date | None, str | None]:
    start = parse_iso(payload.get("start_date"))
    if start is None:
        return None, "Некорректная дата начала"
    if start > date.today():
        return None, "Дата начала не может быть в будущем"
    return start, None


def fill_params(
    payload: dict[str, Any], start: date
) -> tuple[dict[str, Any] | None, str | None]:
    """Параметры режима fill: дата окончания и дни недели (пн=0..вс=6)."""
    end = parse_iso(payload.get("end_date"))
    if end is None:
        return None, "Некорректная дата окончания"
    if end < start:
        return None, "Дата окончания раньше даты начала"
    if end > date.today():
        return None, "Дата окончания не может быть в будущем"
    raw_weekdays = payload.get("weekdays", [])
    if not isinstance(raw_weekdays, list):
        return None, "Выберите хотя бы один день недели"
    raws = cast(list[object], raw_weekdays)
    weekdays = {(d + 6) % 7 for raw in raws if (d := to_int(raw)) is not None}
    if not weekdays:
        return None, "Выберите хотя бы один день недели"
    return {"end": end, "weekdays": weekdays}, None


def text_params(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Параметры режима text: сам текст и шрифт."""
    text = str(payload.get("text", "")).strip()
    if not 1 <= len(text) <= MAX_TEXT_LEN:
        return None, f"Текст: от 1 до {MAX_TEXT_LEN} символов"
    font = str(payload.get("font", DEFAULT_FONT))
    if font not in FONTS:
        return None, f"Неизвестный шрифт: {font}"
    return {"text": text, "font": font}, None


def mode_params(
    payload: dict[str, Any], start: date
) -> tuple[dict[str, Any] | None, str | None]:
    mode = payload.get("mode")
    if mode == "fill":
        return fill_params(payload, start)
    if mode == "text":
        return text_params(payload)
    return None, "Неизвестный режим"


def validate(
    payload: dict[str, Any], need_repo: bool
) -> tuple[dict[str, Any] | None, str | None]:
    """Проверяет параметры формы. Возвращает (параметры, None) или (None, ошибка)."""
    repo, token, repo_error = repo_params(payload)
    if need_repo and repo_error:
        return None, repo_error

    langs = [lang for lang in payload.get("languages", []) if lang in LANGUAGES]
    if not langs:
        return None, f"Выберите хотя бы один язык: {', '.join(sorted(LANGUAGES))}"

    limits, error = commit_range(payload)
    if limits is None:
        return None, error

    start, error = start_date(payload)
    if start is None:
        return None, error

    extra, error = mode_params(payload, start)
    if extra is None:
        return None, error

    ach, error = achievements_params(payload)
    if error:
        return None, error

    params: dict[str, Any] = {
        "repo": repo,
        "token": token,
        "langs": langs,
        "low": limits[0],
        "high": limits[1],
        "start": start,
        "mode": payload.get("mode"),
        "achievements": ach,
    }
    return params | extra, None


def achievements_params(
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Параметры блока ачивок: галочки, тиры и источники соавторов."""
    quickdraw = bool(payload.get("ach_quickdraw"))
    yolo = bool(payload.get("ach_yolo"))
    shark_tier = payload.get("ach_shark_tier")
    pair_tier = payload.get("ach_pair_tier")
    if shark_tier and shark_tier not in achievements.PULL_SHARK_TIERS:
        return None, f"Неизвестный тир Pull Shark: {shark_tier}"
    if pair_tier and pair_tier not in achievements.PAIR_TIERS:
        return None, f"Неизвестный тир Pair Extraordinaire: {pair_tier}"
    raw_friends = str(payload.get("ach_friends", ""))
    friends = [
        login.strip().lstrip("@") for login in raw_friends.split(",") if login.strip()
    ]
    use_bots = bool(payload.get("ach_bots"))
    use_celebs = bool(payload.get("ach_celebs"))
    if pair_tier and not (friends or use_bots or use_celebs):
        return (
            None,
            "Для Pair Extraordinaire выберите источник соавторов: знакомые, сервисные аккаунты или знаменитости",
        )
    if not (quickdraw or yolo or shark_tier or pair_tier):
        return None, None
    params: dict[str, Any] = {
        "quickdraw": quickdraw,
        "yolo": yolo,
        "shark_tier": shark_tier or None,
        "pair_tier": pair_tier or None,
        "friends": friends,
        "use_bots": use_bots,
        "use_celebs": use_celebs,
    }
    return params, None


def make_targets(params: dict[str, Any], rnd: random.Random) -> dict[date, int]:
    # в режиме текста даты могут уходить в будущее: эти клетки
    # закрасятся на таймлайне, когда наступят соответствующие дни
    if params["mode"] == "text":
        return core.text_targets(
            params["text"],
            params["start"],
            params["low"],
            params["high"],
            rnd,
            params["font"],
        )
    return core.fill_targets(
        params["start"],
        params["end"],
        params["weekdays"],
        params["low"],
        params["high"],
        rnd,
    )


@app.get("/")
def index():
    return render_template(
        "index.html",
        languages=sorted(LANGUAGES),
        fonts=FONTS,
        default_font=DEFAULT_FONT,
        owner_coauthor=achievements.OWNER_COAUTHOR,
        bot_coauthors=achievements.BOT_COAUTHORS,
        celeb_coauthors=achievements.CELEB_COAUTHORS,
    )


@app.post("/api/font-preview")
def font_preview():
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    font = str(payload.get("font", DEFAULT_FONT))
    if font not in FONTS:
        return jsonify({"error": f"Неизвестный шрифт: {font}"}), 400
    text = str(payload.get("text", "")).strip()
    if not 1 <= len(text) <= MAX_TEXT_LEN:
        return jsonify({"error": f"Текст: от 1 до {MAX_TEXT_LEN} символов"}), 400
    try:
        columns = render_text(text, load_font(FONTS_DIR / f"{font}.txt"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"columns": columns})


@app.post("/api/preview")
def preview():
    params, error = validate(request.get_json(silent=True) or {}, need_repo=False)
    if params is None:
        return jsonify({"error": error}), 400
    try:
        targets = make_targets(params, random.Random())
    except ValueError as exc:  # неподдерживаемый символ в тексте
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {
            "days": {day.isoformat(): count for day, count in sorted(targets.items())},
            "total": sum(targets.values()),
        }
    )


@app.post("/api/check")
def check():
    repo, token, error = repo_params(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    try:
        branch, heads = core.ls_remote(repo, token)
    except Exception as exc:
        return jsonify({"error": scrub(str(exc), token)}), 400
    if heads == 0:
        return jsonify({"message": "Репозиторий доступен, он пуст"})
    return jsonify({"message": f"Репозиторий доступен, ветка по умолчанию: {branch}"})


def start_job(fn: Callable[[core.Log], int | None], token: str) -> str:
    """Запускает fn(log) в фоне, возвращает id задачи."""
    job_id = uuid.uuid4().hex[:8]
    job = JOBS[job_id] = {"status": "running", "log": [], "created": 0}

    def run() -> None:
        try:
            job["created"] = fn(job["log"].append) or 0
            job["status"] = "done"
        except Exception as exc:
            job["log"].append(f"Ошибка: {scrub(str(exc), token)}")
            job["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.post("/api/push")
def push():
    params, error = validate(request.get_json(silent=True) or {}, need_repo=True)
    if params is None:
        return jsonify({"error": error}), 400
    try:
        targets = make_targets(params, random.Random())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    def job(log: core.Log) -> int:
        def push_timeline() -> int:
            return core.run_push(
                params["repo"], params["token"], params["langs"], targets, log
            )

        ach = params["achievements"]
        if not ach:
            return push_timeline()
        # ачивки первыми: их PR-мерджи попадают в main до того, как пуш
        # таймлайна досчитает остаток по датам; но в пустом репозитории
        # у PR нет базовой ветки — тогда сначала пушим таймлайн
        _, heads = core.ls_remote(params["repo"], params["token"])
        if heads == 0:
            created = push_timeline()
            achievements.run_achievements(params["repo"], params["token"], ach, log)
            return created
        achievements.run_achievements(params["repo"], params["token"], ach, log)
        return push_timeline()

    job_id = start_job(job, params["token"])
    return jsonify({"job": job_id})


@app.post("/api/clear")
def clear():
    repo, token, error = repo_params(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    job_id = start_job(lambda log: core.run_clear(repo, token, log), token)
    return jsonify({"job": job_id})


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Задача не найдена"}), 404
    return jsonify(job)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
