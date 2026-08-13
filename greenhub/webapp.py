"""Веб-интерфейс greenhub отвечает за форму параметров, превью таймлайна и запуск пуша."""

import os
import random
import threading
import uuid
from datetime import date

from flask import Flask, jsonify, render_template, request

import core
from font import FONTS_DIR, available_fonts, load_font, render_text
from snippets import LANGUAGES

app = Flask(__name__)

MAX_COMMITS = 99
MAX_TEXT_LEN = 1000
FONTS = available_fonts()
DEFAULT_FONT = "5x7-pixel-slanted"

JOBS: dict[str, dict] = {}


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


def repo_params(payload: dict) -> tuple[str, str, str | None]:
    """Достаёт и проверяет URL репозитория и токен: (repo, token, ошибка)."""
    repo = str(payload.get("repo", "")).strip()
    token = str(payload.get("token", "")).strip()
    if not repo.startswith("https://"):
        return repo, token, "URL репозитория должен начинаться с https://"
    if not token:
        return repo, token, "Укажите токен"
    return repo, token, None


def scrub(message: str, token: str) -> str:
    """Убирает токен из сообщений git (он попадает в URL в stderr)."""
    return message.replace(token, "***") if token else message


def validate(payload: dict, need_repo: bool) -> tuple[dict | None, str | None]:
    """Проверяет параметры формы. Возвращает (параметры, None) или (None, ошибка)."""
    repo, token, repo_error = repo_params(payload)
    params: dict = {"repo": repo, "token": token}
    if need_repo and repo_error:
        return None, repo_error

    langs = [lang for lang in payload.get("languages", []) if lang in LANGUAGES]
    if not langs:
        return None, f"Выберите хотя бы один язык: {', '.join(sorted(LANGUAGES))}"
    params["langs"] = langs

    if payload.get("random", True):
        low = to_int(payload.get("min_commits", 1))
        high = to_int(payload.get("max_commits", 5))
        if low is None or high is None or not 1 <= low < high <= MAX_COMMITS:
            return None, f"Для случайного режима нужно: 1 ≤ от < до ≤ {MAX_COMMITS}"
    else:
        commits = to_int(payload.get("commits", 1))
        if commits is None or not 1 <= commits <= MAX_COMMITS:
            return None, f"Число коммитов: от 1 до {MAX_COMMITS}"
        low = high = commits
    params["low"], params["high"] = low, high

    today = date.today()
    start = parse_iso(payload.get("start_date"))
    if start is None:
        return None, "Некорректная дата начала"
    if start > today:
        return None, "Дата начала не может быть в будущем"
    params["start"] = start

    mode = payload.get("mode")
    params["mode"] = mode
    if mode == "fill":
        end = parse_iso(payload.get("end_date"))
        if end is None:
            return None, "Некорректная дата окончания"
        if end < start:
            return None, "Дата окончания раньше даты начала"
        if end > today:
            return None, "Дата окончания не может быть в будущем"
        raw_weekdays = payload.get("weekdays", [])
        if not isinstance(raw_weekdays, list) or not raw_weekdays:
            return None, "Выберите хотя бы один день недели"
        weekdays = {(to_int(d) + 6) % 7 for d in raw_weekdays if to_int(d) is not None}
        if not weekdays:
            return None, "Выберите хотя бы один день недели"
        params["end"], params["weekdays"] = end, weekdays
    elif mode == "text":
        text = str(payload.get("text", "")).strip()
        if not 1 <= len(text) <= MAX_TEXT_LEN:
            return None, f"Текст: от 1 до {MAX_TEXT_LEN} символов"
        params["text"] = text
        font = str(payload.get("font", DEFAULT_FONT))
        if font not in FONTS:
            return None, f"Неизвестный шрифт: {font}"
        params["font"] = font
    else:
        return None, "Неизвестный режим"
    return params, None


def make_targets(params: dict, rnd: random.Random) -> dict[date, int]:
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
    )


@app.post("/api/font-preview")
def font_preview():
    payload = request.get_json(silent=True) or {}
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
    if error:
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


def start_job(fn, token: str) -> str:
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
    if error:
        return jsonify({"error": error}), 400
    try:
        targets = make_targets(params, random.Random())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    job_id = start_job(
        lambda log: core.run_push(
            params["repo"], params["token"], params["langs"], targets, log
        ),
        params["token"],
    )
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
