"""Ачивки профиля GitHub: Quickdraw, YOLO, Pull Shark, Pair Extraordinaire.

Все четыре работают через штатный API поверх того же репозитория, куда
greenhub пушит коммиты: issue с быстрым закрытием, PR с мержом без ревью,
серия мерджей и co-authored коммиты в смердженных PR. GitHub начисляет
ачивки с задержкой — результат виден в профиле не сразу.
"""

import base64
import json
import random
import re
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

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

# за один прогон не делаем больше — остаток добирается следующими запусками
MAX_PRS_PER_RUN = 300

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
    payload: dict | None = None,
    ignore_errors: bool = False,
) -> tuple[int, object]:
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
        if ignore_errors:
            return exc.code, {}
        raise ApiError(f"GitHub API {method} {path}: {exc.code} {body[:300]}") from None
    except urllib.error.URLError as exc:
        raise ApiError(f"GitHub API {method} {path}: {exc.reason}") from None


def api_json(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    status, data = api(method, path, token, payload)
    if not isinstance(data, dict):
        raise ApiError(f"GitHub API {method} {path}: неожиданный ответ ({status})")
    return data


def current_user(token: str) -> dict:
    user = api_json("GET", "/user", token)
    return {"login": user["login"], "name": user.get("name") or user["login"]}


def merged_prs(owner: str, name: str, token: str) -> int:
    # ачивка считает только PR самого автора — чужие мерджи в репо не в счёт
    login = current_user(token)["login"]
    data = api_json(
        "GET",
        f"/search/issues?q=repo:{owner}/{name}+type:pr+is:merged+author:{login}&per_page=1",
        token,
    )
    return int(data.get("total_count", 0))


def validate_login(login: str, author_login: str, token: str, log: Log) -> dict | None:
    """Проверяет соавтора через API; возвращает его данные или None с причиной в логе."""
    status, user = api("GET", f"/users/{login}", token)
    if status != 200 or not isinstance(user, dict):
        log(f"Соавтор {login}: аккаунт не найден, пропускаем")
        return None
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
) -> tuple[list[str], list[str], dict[str, dict]]:
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
    info: dict[str, dict] = {}
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


def merge_pr(owner: str, name: str, number: int, token: str) -> None:
    for attempt in range(2):
        try:
            api_json(
                "PUT",
                f"/repos/{owner}/{name}/pulls/{number}/merge",
                token,
                {"merge_method": "merge"},
            )
            return
        except ApiError:
            if attempt == 1:
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


def head_sha(owner: str, name: str, branch: str, token: str) -> str:
    ref = api_json("GET", f"/repos/{owner}/{name}/git/ref/heads/{branch}", token)
    return str(ref["object"]["sha"])


def make_branch(owner: str, name: str, token: str, prefix: str, sha: str) -> str:
    """Создаёт ветку от указанного коммита через REST, подбирая свободное имя."""
    for _ in range(100):
        branch = f"{prefix}-{date.today().isoformat()}-{random.getrandbits(32):08x}"
        status, _ = api(
            "POST",
            f"/repos/{owner}/{name}/git/refs",
            token,
            {"ref": f"refs/heads/{branch}", "sha": sha},
            ignore_errors=True,
        )
        if status == 201:
            return branch
    raise RuntimeError(f"Не удалось подобрать свободное имя ветки {prefix}-*")


def readme_commit(owner: str, name: str, branch: str, token: str, message: str) -> None:
    """Коммит в ветку через Contents API: дописывает строку-маркер в README.

    Не конфликтует с коммитами таймлайна, т.к. те добавляют файлы вида
    ext/дата_N.ext и не трогают README.
    """
    status, info = api(
        "GET",
        f"/repos/{owner}/{name}/contents/README.md?ref={branch}",
        token,
        ignore_errors=True,
    )
    content, sha = "", None
    if status == 200 and isinstance(info, dict) and "sha" in info:
        content = base64.b64decode(info["content"]).decode()
        sha = info["sha"]
    marker = f"{date.today().isoformat()} {random.getrandbits(64):016x}"
    payload: dict = {
        "message": message,
        "content": base64.b64encode(f"{content}\n- {marker}\n".encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    api_json("PUT", f"/repos/{owner}/{name}/contents/README.md", token, payload)


def open_and_merge(
    owner: str, name: str, branch: str, token: str, title: str, base: str
) -> None:
    pr = api_json(
        "POST",
        f"/repos/{owner}/{name}/pulls",
        token,
        {"title": title, "head": branch, "base": base},
    )
    wait_mergeable(owner, name, pr["number"], token)
    merge_pr(owner, name, pr["number"], token)
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


def run_pull_shark(repo_url: str, token: str, need: int, log: Log) -> int:
    """Пустые PR по одному на мерж. need — сколько мерджей не хватает до тира."""
    owner, name = owner_repo(repo_url)
    base = default_branch(owner, name, token)
    with tempfile.TemporaryDirectory(prefix="greenhub-shark-") as work:
        repo = str(Path(work) / "repo")
        core.clone_repo(repo_url, token, repo, log)
        core.configure_git_user(repo, token, log)
        for done in range(1, need + 1):
            branch = make_branch(
                owner, name, token, "greenhub-shark", head_sha(owner, name, base, token)
            )
            core.git(repo, "fetch", "-q", "origin", branch)
            core.git(repo, "checkout", "-q", f"origin/{branch}")
            core.git(repo, "commit", "-q", "--allow-empty", "-m", f"Pull Shark {done}")
            core.git(repo, "push", "-q", "origin", f"HEAD:{branch}")
            open_and_merge(owner, name, branch, token, f"Pull Shark {done}", base)
            if done % 10 == 0:
                log(f"Pull Shark: смерджено {done}/{need}")
    log(f"Pull Shark: смерджено {need} PR")
    return need


def has_open_pair_pr(owner: str, name: str, token: str) -> bool:
    status, data = api(
        "GET", f"/repos/{owner}/{name}/pulls?state=open&per_page=100", token
    )
    return isinstance(data, list) and any(
        str(pr.get("title", "")).startswith("Pair ") for pr in data
    )


def run_pair(
    repo_url: str,
    token: str,
    commits: int,
    friends: list[str],
    use_bots: bool,
    use_celebs: bool,
    log: Log,
) -> int:
    """Co-authored коммиты в смердженных PR: каждый коммит — один трейлер.

    Коммиты идут через Contents API, локальный клон не нужен: фаза не
    зависит от состояния репозитория и не мешает пушу таймлайна.
    """
    owner, name = owner_repo(repo_url)
    author = current_user(token)
    singles, pool, info = resolve_coauthors(
        friends, use_bots, use_celebs, author["login"], token, log
    )
    if not singles and not pool:
        raise RuntimeError("Не осталось ни одного валидного соавтора")
    if has_open_pair_pr(owner, name, token):
        # повторный прогон после падения: незакрытый Pair PR значит, что его
        # коммиты уже на GitHub и в следующий заход досчитаются сами
        log("Pair: найден открытый PR прошлого прогона, пропускаем фазу")
        return 0

    def trailer(login: str) -> str:
        user = info[login]
        # в имени соавтора может оказаться перевод строки — ломал бы формат трейлера
        display = str(user.get("name") or login).replace("\n", " ").strip()
        return f"Co-authored-by: {display} <{user['id']}+{login}@users.noreply.github.com>"

    base = default_branch(owner, name, token)
    created = 0
    for i in range(commits):
        if i < len(singles):
            login = singles[i]
        elif pool and not use_celebs:
            login = random.choice(pool)
        elif i - len(singles) < len(pool):
            login = pool[i - len(singles)]
        else:
            log("Pair: соавторы кончились, повторы отключены")
            break
        branch = make_branch(
            owner, name, token, "greenhub-pair", head_sha(owner, name, base, token)
        )
        message = f"Pair {i + 1}\n\n{trailer(login)}"
        readme_commit(owner, name, branch, token, message)
        try:
            open_and_merge(owner, name, branch, token, f"Pair {i + 1}", base)
        except ApiError as exc:
            # чаще всего конфликт README с соседним мержем: ветка бесплатна,
            # пересоздаём её от свежей дефолтной и повторяем один раз
            log(f"Pair {i + 1}: мерж не удался ({exc}), повторяем на новой ветке")
            delete_ref(owner, name, branch, token)
            branch = make_branch(
                owner, name, token, "greenhub-pair", head_sha(owner, name, base, token)
            )
            readme_commit(owner, name, branch, token, message)
            open_and_merge(owner, name, branch, token, f"Pair {i + 1}", base)
        created += 1
        if created % 10 == 0:
            log(f"Pair: {created}/{commits} co-authored коммитов")
    log(f"Pair: {created} co-authored коммитов в смердженных PR")
    return created


def plan(params: dict, repo_url: str, token: str, log: Log) -> dict:
    """Собирает параметры прогона в план: что и сколько делать."""
    owner, name = owner_repo(repo_url)
    plan_: dict = {
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
    return plan_


def run_achievements(repo_url: str, token: str, params: dict, log: Log) -> None:
    """Прогон ачивок по плану. YOLO выпадает само на первом же мерже."""
    owner, name = owner_repo(repo_url)
    plan_ = plan(params, repo_url, token, log)
    if plan_["quickdraw"]:
        run_quickdraw(owner, name, token, log)
    if plan_["pull_shark"]:
        run_pull_shark(repo_url, token, min(plan_["pull_shark"], MAX_PRS_PER_RUN), log)
    if plan_["pair"]:
        run_pair(
            repo_url,
            token,
            plan_["pair"],
            plan_["friends"],
            plan_["use_bots"],
            plan_["use_celebs"],
            log,
        )
    if plan_["yolo"]:
        if plan_["pull_shark"] or plan_["pair"]:
            log("YOLO: засчитается на первом мерже этого прогона")
        else:
            base = default_branch(owner, name, token)
            branch = make_branch(
                owner, name, token, "greenhub-yolo", head_sha(owner, name, base, token)
            )
            readme_commit(owner, name, branch, token, "YOLO")
            open_and_merge(owner, name, branch, token, "YOLO", base)
            log("YOLO: PR смерджен без ревью")
    log(
        "Ачивки начисляются GitHub с задержкой — проверьте профиль через несколько часов"
    )
