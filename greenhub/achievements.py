"""Ачивки профиля GitHub: Quickdraw, YOLO, Pull Shark, Pair Extraordinaire.

Все четыре работают через штатный API поверх того же репозитория, куда
greenhub пушит коммиты: issue с быстрым закрытием, PR с мержом без ревью,
серия мерджей и co-authored коммиты в смердженных PR. Каждый PR несёт один
обычный сниппет-коммит с датой из свободного дня плана таймлайна и мержится
rebase-ом, так клетки ложатся на запланированные даты, а не в день прогона.
GitHub начисляет ачивки с задержкой и результат виден в профиле не сразу.
"""

import json
import random
import re
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, cast

import core

# сервисные аккаунты с type=User — GitHub считает соавторство только
# с пользователями, организации и [bot]-аккаунты трейлер не привязывает
BOT_COAUTHORS = [
    "cursoragent",
    "claude",
    "codex",
    "snyk-bot",
    "coveralls",
    "weblate",
    "bors-servo",
    "rust-highfive",
    "codecov-io",
    "scala-steward",
    "actions-user",
    "pyup-bot",
    "houndci-bot",
]

CELEB_COAUTHORS = [
    "torvalds",
    "gvanrossum",
    "brendaneich",
    "dhh",
    "mojombo",
    "defunkt",
    "schacon",
    "pjhyett",
    "gaearon",
    "sindresorhus",
    "tj",
    "yyx990803",
    "antirez",
    "fabpot",
    "rauchg",
    "kelseyhightower",
    "addyosmani",
    "paulirish",
    "getify",
    "wesbos",
    "kentcdodds",
    "cassidoo",
    "sdras",
    "una",
    "jakearchibald",
    "Rich-Harris",
    "sebmarkbage",
    "acdlite",
    "sophiebits",
    "bvaughn",
    "kennethreitz",
    "mitchellh",
    "fasterthanlime",
    "brendangregg",
    "jlord",
    "argyleink",
    "wycats",
    "jeresig",
    "douglascrockford",
    "hadley",
    "karpathy",
    "fchollet",
    "soumith",
    "mdo",
    "fat",
    "shiffman",
    "bradfitz",
    "filosottile",
    "robpike",
    "rsc",
]

# владелец сервиса: всегда первый соавтор, строго один раз за прогон
OWNER_COAUTHOR = "thalidzhokov"

PULL_SHARK_TIERS = {"default": 2, "bronze": 16, "silver": 128, "gold": 1024}
PAIR_TIERS = {"default": 1, "bronze": 10, "silver": 24, "gold": 48}

# за один прогон не делаем больше — остаток добирается следующими запусками;
# массовое создание PR упирается в secondary rate limits и правила GitHub
# об automated bulk activity, поэтому лимит консервативный
MAX_PRS_PER_RUN = 128

# пауза между PR: снижает шанс словить secondary rate limit
PR_PAUSE_SECONDS = 2

Log = core.Log


class ApiError(Exception):
    """Ошибка вызова GitHub API с уже очищенным от токена текстом."""


def owner_repo(url: str) -> tuple[str, str]:
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not match:
        raise ValueError(f"Не удалось разобрать URL репозитория: {url}")
    return match.group(1), match.group(2)


def api(
    method: str,
    path: str,
    token: str,
    payload: dict[str, object] | None = None,
    ignore_errors: bool = False,
) -> tuple[int, object]:
    for attempt in range(3):
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read().decode()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            # secondary rate limit: ждём, сколько велено, и повторяем;
            # обычный 403 без Retry-After (нет прав) сюда не попадает
            retry_after = exc.headers.get("Retry-After", "")
            if exc.code in (403, 429) and attempt < 2:
                if retry_after or "secondary rate limit" in body:
                    delay = int(retry_after) if retry_after.isdigit() else 60
                    time.sleep(min(delay, 120))
                    continue
            if ignore_errors:
                return exc.code, {}
            raise ApiError(
                f"GitHub API {method} {path}: {exc.code} {body[:300]}"
            ) from None
        except urllib.error.URLError as exc:
            raise ApiError(f"GitHub API {method} {path}: {exc.reason}") from None
    raise ApiError(f"GitHub API {method} {path}: превышен лимит повторов")


def api_json(
    method: str, path: str, token: str, payload: dict[str, object] | None = None
) -> dict[str, Any]:
    status, data = api(method, path, token, payload)
    if not isinstance(data, dict):
        raise ApiError(f"GitHub API {method} {path}: неожиданный ответ ({status})")
    return cast(dict[str, Any], data)


def current_user(token: str) -> dict[str, Any]:
    user = api_json("GET", "/user", token)
    return {"login": user["login"], "name": user.get("name") or user["login"]}


def probe_permissions(repo_url: str, token: str) -> dict[str, bool]:
    """Проверяет доступ токена к областям Contents, Issues и Pull requests.

    Пробы — безопасные GET: fine-grained токен без права на область отвечает
    401/403. Отличить read от write без побочных эффектов нельзя, поэтому
    нехватка именно write всплывёт позже, в логе прогона.
    """
    owner, name = owner_repo(repo_url)
    probes = {
        # 404 не считается отказом: в пустом репозитории нет README,
        # но право Contents при этом есть
        "contents": f"/repos/{owner}/{name}/contents/README.md",
        "issues": f"/repos/{owner}/{name}/issues?per_page=1",
        "pulls": f"/repos/{owner}/{name}/pulls?per_page=1",
    }
    return {
        key: api("GET", path, token, ignore_errors=True)[0] not in (401, 403)
        for key, path in probes.items()
    }


def merged_prs(owner: str, name: str, token: str) -> int:
    # ачивка считает только PR самого автора — чужие мерджи в репо не в счёт
    login = current_user(token)["login"]
    data = api_json(
        "GET",
        f"/search/issues?q=repo:{owner}/{name}+type:pr+is:merged+author:{login}&per_page=1",
        token,
    )
    return int(data.get("total_count", 0))


def validate_login(
    login: str, author_login: str, token: str, log: Log
) -> dict[str, Any] | None:
    """Проверяет соавтора через API; возвращает его данные или None с причиной в логе."""
    status, data = api("GET", f"/users/{login}", token)
    if status != 200 or not isinstance(data, dict):
        log(f"Соавтор {login}: аккаунт не найден, пропускаем")
        return None
    user = cast(dict[str, Any], data)
    if user.get("type") != "User":
        log(
            f"Соавтор {login}: это {user.get('type')}, соавторство не засчитается, пропускаем"
        )
        return None
    if user["login"].lower() == author_login.lower():
        log(f"Соавтор {login}: совпадает с автором токена, пропускаем")
        return None
    return user


def resolve_coauthors(
    friends: list[str],
    use_bots: bool,
    use_celebs: bool,
    author_login: str,
    token: str,
    log: Log,
) -> tuple[list[str], list[str], dict[str, dict[str, Any]]]:
    """Очередь соавторов: (одиночные, пул, данные аккаунтов).

    Одиночные — владелец сервиса (первый коммит, один раз) и знакомые,
    каждый строго по разу. Пул — сервисные аккаунты и знаменитости,
    перемешаны; повторы разрешены, только когда пул состоит из одних
    сервисных аккаунтов (use_celebs=False).
    """
    pool = (BOT_COAUTHORS if use_bots else []) + (CELEB_COAUTHORS if use_celebs else [])
    random.shuffle(pool)

    seen: set[str] = set()
    singles: list[str] = []
    info: dict[str, dict[str, Any]] = {}
    for login in [OWNER_COAUTHOR, *[f.strip().lstrip("@") for f in friends]]:
        if not login or login.lower() in seen:
            continue
        seen.add(login.lower())
        user = validate_login(login, author_login, token, log)
        if user:
            singles.append(user["login"])
            info[user["login"]] = user

    pool_valid: list[str] = []
    for login in pool:
        if login.lower() in seen:
            continue
        seen.add(login.lower())
        user = validate_login(login, author_login, token, log)
        if user:
            pool_valid.append(user["login"])
            info[user["login"]] = user

    return singles, pool_valid, info


def wait_mergeable(owner: str, name: str, number: int, token: str) -> None:
    # после создания PR GitHub считает mergeable асинхронно — ждём, пока
    # перестанет быть None, иначе мерж падает с 405
    for _ in range(15):
        pr = api_json("GET", f"/repos/{owner}/{name}/pulls/{number}", token)
        if pr.get("mergeable") is not None:
            return
        time.sleep(1)


def merge_pr(owner: str, name: str, number: int, token: str, log: Log) -> None:
    # rebase сохраняет авторские даты коммитов и не создаёт merge-коммит,
    # так что клетки таймлайна остаются на запланированных днях; merge —
    # запасной путь на случай, когда rebase запрещён настройками репозитория
    methods = ("rebase", "rebase", "merge")
    for attempt, method in enumerate(methods):
        try:
            api_json(
                "PUT",
                f"/repos/{owner}/{name}/pulls/{number}/merge",
                token,
                {"merge_method": method},
            )
            if method == "merge":
                log(
                    f"PR #{number}: rebase не прошёл, merge-коммит лёг сегодняшним числом"
                )
            return
        except ApiError:
            if attempt == len(methods) - 1:
                raise
            wait_mergeable(owner, name, number, token)


def delete_ref(owner: str, name: str, branch: str, token: str) -> None:
    api(
        "DELETE",
        f"/repos/{owner}/{name}/git/refs/heads/{branch}",
        token,
        ignore_errors=True,
    )


def default_branch(owner: str, name: str, token: str) -> str:
    return str(api_json("GET", f"/repos/{owner}/{name}", token)["default_branch"])


def open_and_merge(
    owner: str, name: str, branch: str, token: str, title: str, base: str, log: Log
) -> None:
    pr = api_json(
        "POST",
        f"/repos/{owner}/{name}/pulls",
        token,
        {"title": title, "head": branch, "base": base},
    )
    wait_mergeable(owner, name, pr["number"], token)
    merge_pr(owner, name, pr["number"], token, log)
    delete_ref(owner, name, branch, token)


def run_quickdraw(owner: str, name: str, token: str, log: Log) -> None:
    issue = api_json(
        "POST",
        f"/repos/{owner}/{name}/issues",
        token,
        {"title": "Quickdraw", "body": "Закроется в течение пяти минут."},
    )
    log(f"Quickdraw: открыт issue #{issue['number']}")
    time.sleep(61)
    api_json(
        "PATCH",
        f"/repos/{owner}/{name}/issues/{issue['number']}",
        token,
        {"state": "closed"},
    )
    log(f"Quickdraw: issue #{issue['number']} закрыт за ~1 минуту")


def has_open_pair_pr(owner: str, name: str, token: str) -> bool:
    _, data = api("GET", f"/repos/{owner}/{name}/pulls?state=open&per_page=100", token)
    if not isinstance(data, list):
        return False
    prs = cast(list[dict[str, Any]], data)
    return any(str(pr.get("title", "")).startswith("Pair ") for pr in prs)


def coauthor_queue(
    friends: list[str],
    use_bots: bool,
    use_celebs: bool,
    author_login: str,
    count: int,
    token: str,
    log: Log,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Логины соавторов на count коммитов в порядке использования."""
    singles, pool, info = resolve_coauthors(
        friends, use_bots, use_celebs, author_login, token, log
    )
    if not singles and not pool:
        raise RuntimeError("Не осталось ни одного валидного соавтора")
    queue: list[str] = []
    for i in range(count):
        if i < len(singles):
            queue.append(singles[i])
        elif pool and not use_celebs:
            # пул из одних сервисных аккаунтов — повторы разрешены
            queue.append(random.choice(pool))
        elif i - len(singles) < len(pool):
            queue.append(pool[i - len(singles)])
        else:
            log("Pair: соавторы кончились, повторы отключены")
            break
    return queue, info


def trailer(login: str, info: dict[str, dict[str, Any]]) -> str:
    user = info[login]
    # в имени соавтора может оказаться перевод строки — ломал бы формат трейлера
    display = str(user.get("name") or login).replace("\n", " ").strip()
    return f"Co-authored-by: {display} <{user['id']}+{login}@users.noreply.github.com>"


def run_prs(
    repo_url: str,
    token: str,
    plan_: dict[str, Any],
    targets: dict[date, int],
    langs: list[str],
    log: Log,
) -> None:
    """PR-фаза: Pair, Pull Shark и одиночный YOLO одним локальным клоном.

    Каждый PR несёт один сниппет-коммит с датой из свободного дня плана:
    дни раздаются от свежих (не позже сегодня) к прошлым, Pair первым,
    Pull Shark дальше в прошлое. Кончились дни - остаток тира добирается
    следующими прогонами.
    """
    owner, name = owner_repo(repo_url)
    need_pair = plan_["pair"]
    need_shark = min(plan_["pull_shark"], MAX_PRS_PER_RUN)
    need_yolo = 1 if plan_["yolo"] and not (need_pair or need_shark) else 0

    pair_logins: list[str] = []
    info: dict[str, dict[str, Any]] = {}
    if need_pair and has_open_pair_pr(owner, name, token):
        # повторный прогон после падения: незакрытый Pair PR значит, что его
        # коммиты уже на GitHub и в следующий заход досчитаются сами
        log("Pair: найден открытый PR прошлого прогона, пропускаем фазу")
        need_pair = 0
    if need_pair:
        author = current_user(token)
        pair_logins, info = coauthor_queue(
            plan_["friends"],
            plan_["use_bots"],
            plan_["use_celebs"],
            author["login"],
            need_pair,
            token,
            log,
        )
    if not (pair_logins or need_shark or need_yolo):
        return

    base = default_branch(owner, name, token)
    with tempfile.TemporaryDirectory(prefix="greenhub-ach-") as work:
        repo = str(Path(work) / "repo")
        core.clone_repo(repo_url, token, repo, log)
        core.configure_git_user(repo, token, log)
        existing = core.existing_commits(repo)
        counts = core.file_counts(repo, langs)
        try:
            base_sha = core.git(repo, "rev-parse", "HEAD").strip()
        except RuntimeError:
            # пустой репозиторий: PR нужна база — стартовый коммит старой
            # датой и без привязки к аккаунту, чтобы не красить таймлайн
            stamp = "2001-01-01T12:00:00"
            core.git(
                repo,
                "-c",
                "user.name=greenhub",
                "-c",
                "user.email=greenhub@localhost",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "Init",
                extra_env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
            )
            core.git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{base}")
            base_sha = core.git(repo, "rev-parse", "HEAD").strip()

        today = date.today()
        days = [
            day
            for day in sorted(targets, reverse=True)
            if day <= today and targets[day] > existing[day]
        ]
        if len(days) < len(pair_logins):
            log(
                f"Pair: свободных дней в плане {len(days)} на {len(pair_logins)} "
                "соавторов, лишние ждут следующего прогона"
            )
            pair_logins = pair_logins[: len(days)]
        shark_days = days[len(pair_logins) : len(pair_logins) + need_shark]
        if need_shark and len(shark_days) < need_shark:
            log(
                f"Pull Shark: дней хватило на {len(shark_days)} из {need_shark}, "
                "остаток следующим прогоном"
            )
        yolo_days = days[len(pair_logins) + len(shark_days) :][:need_yolo]
        if need_yolo and not yolo_days:
            log("YOLO: в плане нет свободного дня, пропускаем")

        jobs: list[tuple[date, str, str | None]] = [
            (day, f"Pair {i + 1}", trailer(login, info))
            for i, (day, login) in enumerate(zip(days, pair_logins))
        ]
        jobs += [(day, f"Pull Shark {i + 1}", None) for i, day in enumerate(shark_days)]
        jobs += [(day, "YOLO", None) for day in yolo_days]

        for done, (day, title, coauthor) in enumerate(jobs, 1):
            if done > 1:
                time.sleep(PR_PAUSE_SECONDS)
            # наименее заполненный язык — чтобы веса языков оставались равными
            lang = min(langs, key=lambda l: (counts[l], random.random()))
            counts[lang] += 1
            core.git(repo, "checkout", "-q", "--detach", base_sha)
            core.make_commit(repo, lang, day, existing[day], coauthor)
            existing[day] += 1
            branch = f"greenhub-{today.isoformat()}-{random.getrandbits(32):08x}"
            core.git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
            open_and_merge(owner, name, branch, token, title, base, log)
            log(f"PR-мердж: {done}/{len(jobs)}")

    if pair_logins:
        log(f"Pair: {len(pair_logins)} co-authored коммитов в смердженных PR")
    if shark_days:
        log(f"Pull Shark: смерджено {len(shark_days)} PR")
    if yolo_days:
        log("YOLO: PR смерджен без ревью")


def plan(params: dict[str, Any], repo_url: str, token: str, log: Log) -> dict[str, Any]:
    """Собирает параметры прогона в план: что и сколько делать."""
    owner, name = owner_repo(repo_url)
    plan_: dict[str, Any] = {
        "quickdraw": params["quickdraw"],
        "yolo": params["yolo"],
        "friends": params.get("friends", []),
        "use_bots": params.get("use_bots", False),
        "use_celebs": params.get("use_celebs", False),
    }
    shark_tier = params.get("shark_tier")
    if shark_tier:
        target = PULL_SHARK_TIERS[shark_tier]
        have = merged_prs(owner, name, token)
        plan_["pull_shark"] = max(0, target - have)
        log(
            f"Pull Shark: уже смерджено {have}, цель {target}, осталось {plan_['pull_shark']}"
        )
    else:
        plan_["pull_shark"] = 0
    if params.get("pair_tier"):
        if not (plan_["friends"] or plan_["use_bots"] or plan_["use_celebs"]):
            log("Pair: ни один источник соавторов не выбран, пропускаем")
            plan_["pair"] = 0
        else:
            plan_["pair"] = PAIR_TIERS[params["pair_tier"]]
    else:
        plan_["pair"] = 0
    if plan_["pull_shark"] and plan_["pair"]:
        # GitHub засчитает Pair PR в Pull Shark
        # Если Pair по факту меньше, следующий прогон доберёт
        plan_["pull_shark"] = max(0, plan_["pull_shark"] - plan_["pair"])
        log(
            f"Pull Shark: {plan_['pair']} PR закроет Pair, "
            f"отдельных нужно {plan_['pull_shark']}"
        )
    return plan_


def run_achievements(
    repo_url: str,
    token: str,
    params: dict[str, Any],
    targets: dict[date, int],
    langs: list[str],
    log: Log,
) -> None:
    """Прогон ачивок по плану. YOLO выпадает само на первом же мерже."""
    owner, name = owner_repo(repo_url)
    plan_ = plan(params, repo_url, token, log)
    if plan_["quickdraw"]:
        run_quickdraw(owner, name, token, log)
    if plan_["yolo"] and (plan_["pull_shark"] or plan_["pair"]):
        log("YOLO: засчитается на первом мерже этого прогона")
    if plan_["pull_shark"] or plan_["pair"] or plan_["yolo"]:
        run_prs(repo_url, token, plan_, targets, langs, log)
    log(
        "Ачивки начисляются GitHub с задержкой — проверьте профиль через несколько часов"
    )
