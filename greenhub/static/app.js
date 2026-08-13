"use strict";

const $ = (id) => document.getElementById(id);

const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const COMMIT_FORMS = ["коммит", "коммита", "коммитов"];
const CELL_STEP = 13; // --cell + --gap из style.css

let currentTab = "fill";
let lastPreviewTotal = null;

// локальная дата в ISO, без сдвига в UTC
const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fromIso = (s) => new Date(s + "T00:00:00");

function plural(n, forms) {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return forms[0];
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1];
  return forms[2];
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// --- инициализация формы ---

const now = new Date();
const yearAgo = new Date(now);
yearAgo.setFullYear(yearAgo.getFullYear() - 1);
$("start-date").value = iso(yearAgo);
$("end-date").value = iso(now);

$("random").addEventListener("change", () => {
  $("random-range").classList.toggle("hidden", !$("random").checked);
  $("fixed-count").classList.toggle("hidden", $("random").checked);
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentTab = tab.dataset.tab;
    $("tab-fill").classList.toggle("hidden", currentTab !== "fill");
    $("tab-text").classList.toggle("hidden", currentTab !== "text");
  });
});

function showError(message) {
  const node = $("form-error");
  node.textContent = message;
  node.classList.remove("hidden");
}

function hideError() {
  $("form-error").classList.add("hidden");
}

function collectParams() {
  const params = {
    repo: $("repo").value.trim(),
    token: $("token").value.trim(),
    languages: [...document.querySelectorAll("#languages input:checked")].map((i) => i.value),
    random: $("random").checked,
    start_date: $("start-date").value,
    mode: currentTab,
  };
  if (params.random) {
    params.min_commits = $("min-commits").valueAsNumber;
    params.max_commits = $("max-commits").valueAsNumber;
  } else {
    params.commits = $("commits").valueAsNumber;
  }
  if (currentTab === "fill") {
    params.end_date = $("end-date").value;
    params.weekdays = [...document.querySelectorAll("#weekdays input:checked")].map((i) => Number(i.value));
  } else {
    params.text = $("text").value;
  }
  return params;
}

async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

// --- превью ---

const levelOf = (count, maxCount) =>
  count ? Math.min(4, Math.ceil((count / maxCount) * 4)) : 0;

function sundayOf(d) {
  const s = new Date(d);
  s.setDate(s.getDate() - s.getDay());
  return s;
}

function buildCalendar(first, last, days, maxCount, title) {
  const cal = el("div", "calendar");
  cal.append(el("div", "cal-title", title));

  const body = el("div", "cal-body");
  const months = el("div", "months");
  const grid = el("div", "cal-grid");
  const wdLabels = el("div", "wd-labels");
  ["", "пн", "", "ср", "", "пт", ""].forEach((t) => wdLabels.append(el("span", "wd", t)));
  const weeks = el("div", "weeks");

  let prevMonth = -1;
  let col = 0;
  for (let w = sundayOf(first); w <= last; w.setDate(w.getDate() + 7), col++) {
    const week = el("div", "week");
    let firstVisibleMonth = -1;
    for (let d = 0; d < 7; d++) {
      const day = new Date(w);
      day.setDate(day.getDate() + d);
      const cell = el("span", "day");
      if (day < first || day > last) {
        cell.classList.add("blank");
      } else {
        if (firstVisibleMonth < 0) firstVisibleMonth = day.getMonth();
        const key = iso(day);
        const count = days[key] || 0;
        cell.dataset.level = levelOf(count, maxCount);
        cell.title = count
          ? `${key}: ${count} ${plural(count, COMMIT_FORMS)}`
          : `${key}: нет коммитов`;
      }
      week.append(cell);
    }
    if (firstVisibleMonth >= 0 && firstVisibleMonth !== prevMonth) {
      const label = el("span", null, MONTHS[firstVisibleMonth]);
      label.style.left = `${col * CELL_STEP}px`;
      months.append(label);
      prevMonth = firstVisibleMonth;
    }
    weeks.append(week);
  }

  grid.append(wdLabels, weeks);
  body.append(months, grid);

  const legend = el("div", "legend", "меньше");
  for (let i = 0; i <= 4; i++) {
    const cell = el("span", "day");
    cell.dataset.level = i;
    legend.append(cell);
  }
  legend.append("больше");
  body.append(legend);

  cal.append(body);
  return cal;
}

function renderPreview(data) {
  const days = data.days;
  const dates = Object.keys(days).sort();
  const container = $("calendars");
  container.innerHTML = "";

  $("preview-title").textContent = `Превью: ${data.total} ${plural(data.total, COMMIT_FORMS)}`;
  $("preview").classList.remove("hidden");

  if (!dates.length) {
    container.append(el("p", "muted", "Ни один день не попадает в диапазон до сегодняшней даты."));
    return;
  }

  const maxCount = Math.max(...Object.values(days));
  const first = fromIso(dates[0]);
  const last = fromIso(dates[dates.length - 1]);
  const spanDays = (last - first) / 86400000;

  if (spanDays <= 371) {
    // диапазон до года — один календарь «последний год», как на профиле GitHub
    const today = new Date();
    const rollingStart = new Date(today);
    rollingStart.setDate(rollingStart.getDate() - 364);
    const gridFirst = first < rollingStart ? first : rollingStart;
    container.append(buildCalendar(gridFirst, today, days, maxCount, "Последний год"));
  } else {
    for (let year = first.getFullYear(); year <= last.getFullYear(); year++) {
      const yearTotal = dates
        .filter((d) => Number(d.slice(0, 4)) === year)
        .reduce((sum, d) => sum + days[d], 0);
      container.append(
        buildCalendar(
          new Date(year, 0, 1),
          new Date(year, 11, 31),
          days,
          maxCount,
          `${year} — ${yearTotal} ${plural(yearTotal, COMMIT_FORMS)}`
        )
      );
    }
  }
}

$("preview-btn").addEventListener("click", async () => {
  hideError();
  try {
    const data = await postJSON("/api/preview", collectParams());
    lastPreviewTotal = data.total;
    renderPreview(data);
  } catch (exc) {
    showError(exc.message);
  }
});

// --- пуш ---

function setRunning(running) {
  for (const id of ["preview-btn", "push-btn", "check-btn", "clear-btn"]) {
    $(id).disabled = running;
  }
}

function startJobUI(jobId, title, doneTitle) {
  $("job").classList.remove("hidden");
  $("job-title").textContent = title;
  $("job-log").textContent = "";
  setRunning(true);
  pollJob(jobId, doneTitle);
}

async function pollJob(jobId, doneTitle) {
  const logEl = $("job-log");
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    let job;
    try {
      const resp = await fetch(`/api/jobs/${jobId}`);
      job = await resp.json();
      if (!resp.ok) throw new Error(job.error || `HTTP ${resp.status}`);
    } catch (exc) {
      $("job-title").textContent = "Потеряна связь с сервером";
      setRunning(false);
      return;
    }
    logEl.textContent = job.log.join("\n");
    logEl.scrollTop = logEl.scrollHeight;
    if (job.status !== "running") {
      $("job-title").textContent = job.status === "done" ? doneTitle(job) : "Ошибка";
      setRunning(false);
      return;
    }
  }
}

$("push-btn").addEventListener("click", async () => {
  hideError();
  const params = collectParams();
  const estimate =
    lastPreviewTotal === null
      ? "Превью не запускали, число коммитов неизвестно"
      : `По последнему превью будет создано ~${lastPreviewTotal} ${plural(lastPreviewTotal, COMMIT_FORMS)}`;
  if (!confirm(`${estimate}.\nПушим в ${params.repo || "репозиторий"}?`)) return;
  try {
    const { job } = await postJSON("/api/push", params);
    startJobUI(job, "Пушим коммиты…", (j) => `Готово: ${j.created} ${plural(j.created, COMMIT_FORMS)}`);
  } catch (exc) {
    showError(exc.message);
  }
});

// --- проверка и очистка репозитория ---

function repoStatus(ok, message) {
  const node = $("repo-status");
  node.className = `status ${ok ? "ok" : "fail"}`;
  node.textContent = message;
}

$("check-btn").addEventListener("click", async () => {
  repoStatus(true, "Проверяем…");
  try {
    const data = await postJSON("/api/check", {
      repo: $("repo").value.trim(),
      token: $("token").value.trim(),
    });
    repoStatus(true, data.message);
  } catch (exc) {
    repoStatus(false, exc.message);
  }
});

$("clear-btn").addEventListener("click", async () => {
  const repo = $("repo").value.trim();
  if (!confirm(`Вся история коммитов в ${repo || "репозитории"} будет безвозвратно перезаписана.\nПродолжить?`)) return;
  try {
    const { job } = await postJSON("/api/clear", {
      repo,
      token: $("token").value.trim(),
    });
    startJobUI(job, "Очищаем репозиторий…", () => "Репозиторий очищен");
  } catch (exc) {
    showError(exc.message);
  }
});
