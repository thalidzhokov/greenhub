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

function syncAchievements() {
  // права токена неизвестны до проверки репо — тогда блок доступен как раньше
  const achOk = !perms || (perms.issues && perms.pulls);
  for (const id of ["ach-quickdraw", "ach-yolo", "ach-shark", "ach-pair", "ach-friends", "ach-bots", "ach-celebs"]) {
    $(id).disabled = !achOk;
  }
  $("ach-shark-tier").disabled = !achOk || !$("ach-shark").checked;
  $("ach-pair-tier").disabled = !achOk || !$("ach-pair").checked;
  $("pair-options").classList.toggle("hidden", !$("ach-pair").checked);
}

$("ach-shark").addEventListener("change", syncAchievements);
$("ach-pair").addEventListener("change", syncAchievements);

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentTab = tab.dataset.tab;
    $("tab-fill").classList.toggle("hidden", currentTab !== "fill");
    $("tab-text").classList.toggle("hidden", currentTab !== "text");
    saveForm();
  });
});

// --- превью шрифта ---

let fontPreviewTimer;

async function updateFontPreview() {
  const box = $("font-preview");
  const text = $("text").value.trim();
  if (!text) {
    box.innerHTML = "";
    return;
  }
  try {
    const data = await postJSON("/api/font-preview", { text, font: $("font").value });
    box.innerHTML = "";
    for (const column of data.columns) {
      const week = el("div", "week");
      for (const filled of column) {
        const cell = el("span", "day");
        if (filled) cell.dataset.level = 4;
        week.append(cell);
      }
      box.append(week);
    }
  } catch (exc) {
    box.innerHTML = "";
    box.append(el("span", "error-inline", exc.message));
  }
}

$("font").addEventListener("change", updateFontPreview);
$("text").addEventListener("input", () => {
  clearTimeout(fontPreviewTimer);
  fontPreviewTimer = setTimeout(updateFontPreview, 300);
});

// --- состояние кнопок ---

let running = false;
let repoVerified = false; // репозиторий успешно проверен для текущих URL и токена
let perms = null; // права токена из последней проверки репо, null — не проверялись

function updateButtons() {
  const hasCreds = $("repo").value.trim() && $("token").value.trim();
  const contentsOk = !perms || perms.contents;
  $("preview-btn").disabled = running;
  $("check-btn").disabled = running || !hasCreds;
  $("clear-btn").disabled = running || !repoVerified || !contentsOk;
  $("push-btn").disabled = running || !repoVerified || !contentsOk;
}

for (const id of ["repo", "token"]) {
  $(id).addEventListener("input", () => {
    repoVerified = false;
    perms = null;
    syncAchievements();
    updateButtons();
  });
}
updateButtons();

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
    params.font = $("font").value;
  }
  // заблокированный из-за прав токена блок ачивок в прогон не попадает
  const achEnabled = !$("ach-quickdraw").disabled;
  params.ach_quickdraw = achEnabled && $("ach-quickdraw").checked;
  params.ach_yolo = achEnabled && $("ach-yolo").checked;
  params.ach_shark_tier = achEnabled && $("ach-shark").checked ? $("ach-shark-tier").value : null;
  params.ach_pair_tier = achEnabled && $("ach-pair").checked ? $("ach-pair-tier").value : null;
  params.ach_friends = $("ach-friends").value;
  params.ach_bots = $("ach-bots").checked;
  params.ach_celebs = $("ach-celebs").checked;
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

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function dayCell(day, first, last, days, maxCount) {
  const cell = el("span", "day");
  if (day < first || day > last) {
    cell.classList.add("blank");
    return cell;
  }
  const key = iso(day);
  const count = days[key] || 0;
  cell.dataset.level = levelOf(count, maxCount);
  cell.title = count
    ? `${key}: ${count} ${plural(count, COMMIT_FORMS)}`
    : `${key}: нет коммитов`;
  return cell;
}

function buildWeek(weekStart, first, last, days, maxCount) {
  const week = el("div", "week");
  for (let d = 0; d < 7; d++) {
    week.append(dayCell(addDays(weekStart, d), first, last, days, maxCount));
  }
  return week;
}

// месяц первого непустого дня недели, -1 если вся неделя вне диапазона
function firstVisibleMonth(weekStart, first, last) {
  for (let d = 0; d < 7; d++) {
    const day = addDays(weekStart, d);
    if (day >= first && day <= last) return day.getMonth();
  }
  return -1;
}

function buildWeekdayLabels() {
  const wdLabels = el("div", "wd-labels");
  ["", "пн", "", "ср", "", "пт", ""].forEach((t) => wdLabels.append(el("span", "wd", t)));
  return wdLabels;
}

function buildLegend() {
  const legend = el("div", "legend", "меньше");
  for (let i = 0; i <= 4; i++) {
    const cell = el("span", "day");
    cell.dataset.level = i;
    legend.append(cell);
  }
  legend.append("больше");
  return legend;
}

function buildCalendar(first, last, days, maxCount, title) {
  const months = el("div", "months");
  const weeks = el("div", "weeks");
  let prevMonth = -1;
  let col = 0;
  for (let w = sundayOf(first); w <= last; w = addDays(w, 7), col++) {
    weeks.append(buildWeek(w, first, last, days, maxCount));
    const month = firstVisibleMonth(w, first, last);
    if (month >= 0 && month !== prevMonth) {
      const label = el("span", null, MONTHS[month]);
      label.style.left = `${col * CELL_STEP}px`;
      months.append(label);
      prevMonth = month;
    }
  }

  const grid = el("div", "cal-grid");
  grid.append(buildWeekdayLabels(), weeks);
  const body = el("div", "cal-body");
  body.append(months, grid, buildLegend());
  const cal = el("div", "calendar");
  cal.append(el("div", "cal-title", title), body);
  return cal;
}

function yearCalendar(year, days, dates, maxCount) {
  const yearTotal = dates
    .filter((d) => Number(d.slice(0, 4)) === year)
    .reduce((sum, d) => sum + days[d], 0);
  return buildCalendar(
    new Date(year, 0, 1),
    new Date(year, 11, 31),
    days,
    maxCount,
    `${year} — ${yearTotal} ${plural(yearTotal, COMMIT_FORMS)}`
  );
}

function buildCalendars(days, dates) {
  const maxCount = Math.max(...Object.values(days));
  const first = fromIso(dates[0]);
  const last = fromIso(dates[dates.length - 1]);
  const spanDays = (last - first) / 86400000;
  const today = new Date();

  if (spanDays <= 371 && last <= today) {
    // диапазон до года в прошлом — один календарь «последний год», как на профиле GitHub
    const rollingStart = addDays(today, -364);
    const gridFirst = first < rollingStart ? first : rollingStart;
    return [buildCalendar(gridFirst, today, days, maxCount, "Последний год")];
  }
  // план шире года или уходит в будущее — отдельный календарь на каждый год
  const calendars = [];
  for (let year = first.getFullYear(); year <= last.getFullYear(); year++) {
    calendars.push(yearCalendar(year, days, dates, maxCount));
  }
  return calendars;
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
  container.append(...buildCalendars(days, dates));
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

function setRunning(value) {
  running = value;
  updateButtons();
}

function startJobUI(panel, jobId, title) {
  $(panel).classList.remove("hidden");
  $(`${panel}-log`).textContent = title;
  setRunning(true);
  pollJob(panel, jobId);
}

async function pollJob(panel, jobId) {
  const logEl = $(`${panel}-log`);
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    let job;
    try {
      const resp = await fetch(`/api/jobs/${jobId}`);
      job = await resp.json();
      if (!resp.ok) throw new Error(job.error || `HTTP ${resp.status}`);
    } catch (exc) {
      logEl.textContent += "\nПотеряна связь с сервером";
      setRunning(false);
      return;
    }
    if (job.log.length) {
      logEl.textContent = job.log.join("\n");
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (job.status !== "running") {
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
    startJobUI("push-job", job, "Пушим коммиты...");
  } catch (exc) {
    showError(exc.message);
  }
});

// --- проверка и очистка репозитория ---

$("check-btn").addEventListener("click", async () => {
  const logEl = $("repo-job-log");
  $("repo-job").classList.remove("hidden");
  logEl.textContent = `Проверяем ${$("repo").value.trim()}`;
  $("check-btn").disabled = true;
  try {
    const data = await postJSON("/api/check", {
      repo: $("repo").value.trim(),
      token: $("token").value.trim(),
    });
    logEl.textContent += `\n${data.message}`;
    repoVerified = true;
    perms = data.permissions || null;
  } catch (exc) {
    logEl.textContent += `\nОшибка: ${exc.message}`;
    repoVerified = false;
    perms = null;
  }
  syncAchievements();
  updateButtons();
});

$("clear-btn").addEventListener("click", async () => {
  const repo = $("repo").value.trim();
  if (!confirm(`Вся история коммитов в ${repo || "репозитории"} будет безвозвратно перезаписана.\nПродолжить?`)) return;
  try {
    const { job } = await postJSON("/api/clear", {
      repo,
      token: $("token").value.trim(),
    });
    startJobUI("repo-job", job, "Очищаем репозиторий...");
  } catch (exc) {
    showError(exc.message);
  }
});

// --- сохранение формы между перезагрузками страницы ---

const STORAGE_KEY = "greenhub-form";
const TEXT_FIELDS = ["repo", "token", "min-commits", "max-commits", "commits", "start-date", "end-date", "text", "ach-friends"];
const ACH_FIELDS = ["ach-quickdraw", "ach-yolo", "ach-shark", "ach-pair", "ach-bots", "ach-celebs"];

const checkStates = (containerId) =>
  Object.fromEntries(
    [...document.querySelectorAll(`#${containerId} input`)].map((i) => [i.value, i.checked])
  );

function saveForm() {
  const state = {
    fields: Object.fromEntries(TEXT_FIELDS.map((id) => [id, $(id).value])),
    random: $("random").checked,
    font: $("font").value,
    languages: checkStates("languages"),
    weekdays: checkStates("weekdays"),
    ach: Object.fromEntries(ACH_FIELDS.map((id) => [id, $(id).checked])),
    ach_shark_tier: $("ach-shark-tier").value,
    ach_pair_tier: $("ach-pair-tier").value,
    tab: currentTab,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function restoreForm() {
  let state;
  try {
    state = JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch {
    return;
  }
  if (!state) return;
  for (const [id, value] of Object.entries(state.fields || {})) {
    const input = $(id);
    if (input && typeof value === "string") input.value = value;
  }
  $("random").checked = state.random ?? true;
  $("random").dispatchEvent(new Event("change"));
  if ([...$("font").options].some((o) => o.value === state.font)) $("font").value = state.font;
  for (const [containerId, saved] of [["languages", state.languages], ["weekdays", state.weekdays]]) {
    for (const input of document.querySelectorAll(`#${containerId} input`)) {
      if (saved && input.value in saved) input.checked = saved[input.value];
    }
  }
  for (const id of ACH_FIELDS) {
    if (state.ach && id in state.ach) $(id).checked = state.ach[id];
  }
  if (state.ach_shark_tier) $("ach-shark-tier").value = state.ach_shark_tier;
  if (state.ach_pair_tier) $("ach-pair-tier").value = state.ach_pair_tier;
  syncAchievements();
  if (state.tab === "text") document.querySelector('.tab[data-tab="text"]').click();
}

restoreForm();
updateButtons();
updateFontPreview();
document.addEventListener("input", saveForm);
document.addEventListener("change", saveForm);
