"use strict";

const viewState = {
  selectedRunId: null,
  compareIds: new Set(),
  latestRuns: [],
  activeSession: null,
  deferredInstallPrompt: null,
};

function getToken() {
  return localStorage.getItem("cp_token") || "";
}

function promptToken() {
  const token = window.prompt("Enter control panel token (leave blank to clear):", getToken());
  if (token === null) return;
  if (token.trim() === "") {
    localStorage.removeItem("cp_token");
    toast("Token cleared");
  } else {
    localStorage.setItem("cp_token", token.trim());
    toast("Token saved");
  }
  renderTokenStatus();
  refreshAll();
}

function renderTokenStatus() {
  document.getElementById("token-status").textContent = getToken() ? "Saved" : "Not set";
}

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = "Bearer " + token;
  return headers;
}

async function api(method, path, body) {
  const options = { method, headers: authHeaders() };
  if (body !== undefined) options.body = JSON.stringify(body);
  try {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { error: "Network error: " + error.message } };
  }
}

let toastTimer;
function toast(message, isError) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.remove("hidden");
  element.classList.toggle("toast-error", !!isError);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.add("hidden"), 2800);
}

function fmtDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function fmtNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function fmtCurrency(value) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(value));
}

function prettifyJson(value) {
  if (!value) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function setBadge(element, text, className) {
  element.textContent = text;
  element.className = "badge " + className;
}

function renderStatus(status) {
  const statusBadge = document.getElementById("status-badge");
  const modeBadge = document.getElementById("mode-badge");
  const ksBadge = document.getElementById("ks-badge");
  const resetButton = document.getElementById("btn-killswitch-reset");

  setBadge(statusBadge, status.running ? "Running" : "Stopped", status.running ? "badge-running" : "badge-stopped");
  setBadge(modeBadge, status.mode === "live" ? "Live" : "Paper", status.mode === "live" ? "badge-live" : "badge-paper");
  ksBadge.classList.toggle("hidden", !status.kill_switch_active);
  resetButton.classList.toggle("hidden", !status.kill_switch_active);

  document.getElementById("started-at").textContent = fmtDate(status.started_at);
  document.getElementById("stopped-at").textContent = fmtDate(status.stopped_at);
  document.getElementById("last-signal").textContent = status.last_signal ? (status.last_signal.symbol || status.last_signal.note || "Logged") : "—";
  document.getElementById("last-trade").textContent = status.last_trade ? (status.last_trade.symbol || fmtCurrency(status.last_trade.net_pnl)) : "—";

  document.getElementById("hero-title").textContent = status.running ? "Bot is active" : "Ready to trade";
  document.getElementById("hero-subtitle").textContent =
    status.active_paper_run_id
      ? "Paper session is actively logging into the database."
      : "Persistent history, backtests, and paper runs in one app.";
}

function renderDataset(dataset) {
  document.getElementById("dataset-path").textContent = dataset.path || "—";
  document.getElementById("dataset-range").textContent = dataset.start_at && dataset.end_at
    ? `${fmtDate(dataset.start_at)} → ${fmtDate(dataset.end_at)}`
    : "—";
  document.getElementById("dataset-count").textContent = fmtNumber(dataset.total_candles);
}

function selectedMarketQuery() {
  const form = document.getElementById("backtest-form");
  const query = new URLSearchParams({
    exchange: form.elements.exchange.value,
    symbol: form.elements.symbol.value,
    timeframe: form.elements.timeframe.value,
  });
  return query.toString();
}

async function refreshMarketDataStatus() {
  const { ok, data } = await api("GET", `/api/market-data/status?${selectedMarketQuery()}`);
  if (!ok) {
    document.getElementById("cache-status").textContent = "Unavailable";
    document.getElementById("cache-updated").textContent = "—";
    return;
  }
  document.getElementById("cache-status").textContent = data.exists === false ? "Not cached" : "Cached";
  document.getElementById("cache-updated").textContent = fmtDate(data.updated_at);
}

function renderMarketOptions(options = {}) {
  const fields = [
    ["backtest-exchange", options.exchanges || [], "binance", "Binance"],
    ["backtest-market-type", options.market_types || [], "spot", "Spot"],
    ["backtest-timeframe", options.timeframes || [], "csv", "Dataset timeframe"],
  ];
  for (const [id, values, fallbackValue, fallbackLabel] of fields) {
    const select = document.getElementById(id);
    const currentValue = select.value;
    const availableValues = values.length ? values : [fallbackValue];
    select.innerHTML = availableValues.map((value) => {
      const label = value === fallbackValue ? fallbackLabel : value;
      return `<option value="${value}">${label}</option>`;
    }).join("");
    select.value = availableValues.includes(currentValue) ? currentValue : availableValues[0];
  }
  const symbolInput = document.getElementById("backtest-symbol");
  const symbolList = document.getElementById("backtest-symbol-options");
  symbolList.innerHTML = (options.symbols || []).map((symbol) => `<option value="${symbol}"></option>`).join("");
  if (!symbolInput.value) symbolInput.value = options.symbols?.[0] || "sample";
  syncMarketSelection();
}

function syncMarketSelection() {
  const symbolInput = document.getElementById("backtest-symbol");
  const timeframe = document.getElementById("backtest-timeframe");
  if (symbolInput.value === "sample") {
    timeframe.value = "csv";
  } else if (timeframe.value === "csv") {
    timeframe.value = "1h";
  }
}

function showScreen(name) {
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.toggle("active", screen.id === `screen-${name}`);
  });
  document.querySelectorAll(".tabbar-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.screen === name);
  });
}

function collectFormData(form) {
  const raw = {};
  for (const element of form.elements) {
    if (!element.name || element.disabled) continue;
    if (element.type === "button" || element.type === "submit") continue;
    if (element.value === "") continue;
    if (element.type === "number") raw[element.name] = Number(element.value);
    else raw[element.name] = element.value;
  }
  return raw;
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function applyDatePreset(days) {
  const form = document.getElementById("backtest-form");
  const start = form.elements.start_date;
  const end = form.elements.end_date;
  if (days === "clear") {
    start.value = "";
    end.value = "";
    return;
  }
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - Number(days));
  start.value = formatDateInput(startDate);
  end.value = formatDateInput(endDate);
}

function nestDotKeys(payload) {
  const nested = {};
  for (const [key, value] of Object.entries(payload)) {
    const parts = key.split(".");
    let pointer = nested;
    while (parts.length > 1) {
      const part = parts.shift();
      pointer[part] = pointer[part] || {};
      pointer = pointer[part];
    }
    pointer[parts[0]] = value;
  }
  return nested;
}

async function refreshStatusOnly() {
  const { ok, data } = await api("GET", "/api/status");
  if (ok) renderStatus(data);
}

async function refreshApp() {
  const { ok, data } = await api("GET", "/api/app");
  if (!ok) {
    if (data.error) toast(data.error, true);
    return;
  }
  renderStatus(data.state);
  renderDataset(data.dataset);
  renderMarketOptions(data.market_options);
  await refreshMarketDataStatus();
  viewState.latestRuns = data.recent_runs || [];
  renderRunCards(document.getElementById("dashboard-runs"), viewState.latestRuns, { compact: true });
}

async function refreshAll() {
  await Promise.all([refreshApp(), loadLogs(), loadRuns(), loadPaperSession(), loadCurrentSettings()]);
}

async function botAction(action) {
  const { ok, data } = await api("POST", `/api/${action}`);
  if (ok) {
    renderStatus(data.status);
    toast(data.message || `${action} complete`);
    if (data.paper_session) renderRunDetail(data.paper_session);
    await refreshAll();
  } else {
    toast(data.error || "Request failed", true);
  }
}

async function setMode(mode) {
  if (mode === "live") {
    const confirmLive = window.prompt("Type LIVE to confirm switching to live mode:", "");
    if (confirmLive !== "LIVE") {
      toast("Live mode not activated");
      return;
    }
    const { ok, data } = await api("POST", "/api/mode/confirm-live", { confirm: "LIVE" });
    ok ? toast(data.message || "Live mode enabled", true) : toast(data.error || "Error", true);
    await refreshAll();
    return;
  }
  const { ok, data } = await api("POST", "/api/mode/paper");
  ok ? toast(data.message || "Paper mode enabled") : toast(data.error || "Error", true);
  await refreshAll();
}

async function triggerKillSwitch() {
  if (!window.confirm("Activate the kill switch and stop the bot immediately?")) return;
  await botAction("killswitch");
}

async function resetKillSwitch() {
  const { ok, data } = await api("POST", "/api/killswitch/reset");
  ok ? toast(data.message || "Kill switch reset") : toast(data.error || "Error", true);
  await refreshAll();
}

async function submitBacktest(event) {
  event.preventDefault();
  const raw = collectFormData(event.target);
  if ((raw.start_date && !raw.end_date) || (!raw.start_date && raw.end_date)) {
    toast("Choose both a start and end date, or leave both blank", true);
    return;
  }
  if (raw.start_date && raw.end_date && raw.start_date > raw.end_date) {
    toast("Start date must be before end date", true);
    return;
  }
  const payload = {
    title: raw.title,
    exchange: raw.exchange,
    market_type: raw.market_type,
    symbol: raw.symbol,
    timeframe: raw.timeframe,
    start_date: raw.start_date,
    end_date: raw.end_date,
    notes: raw.notes,
    config_overrides: nestDotKeys(Object.fromEntries(
      Object.entries(raw).filter(([key]) => key.startsWith("config_overrides."))
        .map(([key, value]) => [key.replace("config_overrides.", ""), value])
    )),
  };
  if (!Object.keys(payload.config_overrides).length) delete payload.config_overrides;

  const msg = document.getElementById("backtest-msg");
  msg.classList.add("hidden");
  const { ok, data } = await api("POST", "/api/backtests", payload);
  if (!ok) {
    msg.textContent = (data.errors || [data.error || "Backtest failed"]).join("; ");
    msg.className = "inline-msg error";
    toast("Backtest failed", true);
    return;
  }
  msg.textContent = `Saved run ${data.id}`;
  msg.className = "inline-msg success";
  renderRunDetail(data);
  document.getElementById("backtest-result").innerHTML = runDetailMarkup(data);
  toast("Backtest completed");
  await refreshAll();
  showScreen("history");
}

function renderPaperSession(session) {
  const container = document.getElementById("paper-session-summary");
  viewState.activeSession = session;
  if (!session) {
    container.className = "empty-state";
    container.textContent = "No active paper session.";
    return;
  }
  container.className = "session-summary";
  container.innerHTML = `
    <div class="session-pill">${session.title}</div>
    <div class="summary-grid">
      <div><span class="info-label">Run ID</span><strong>${session.id}</strong></div>
      <div><span class="info-label">Status</span><strong>${session.status}</strong></div>
      <div><span class="info-label">Events</span><strong>${fmtNumber(session.event_count)}</strong></div>
      <div><span class="info-label">Trades</span><strong>${fmtNumber(session.trade_count)}</strong></div>
    </div>
  `;
}

async function loadPaperSession() {
  const { ok, data } = await api("GET", "/api/paper/session");
  if (ok) renderPaperSession(data.session);
}

async function startPaperSession(event) {
  event.preventDefault();
  const payload = collectFormData(event.target);
  const { ok, data } = await api("POST", "/api/paper/start", payload);
  ok ? toast("Paper session started") : toast(data.error || "Unable to start paper session", true);
  if (ok) renderPaperSession(data);
  await refreshAll();
}

async function stopPaperSession() {
  const note = window.prompt("Add a closing note for this paper session (optional):", "") || "";
  const { ok, data } = await api("POST", "/api/paper/stop", { notes: note });
  ok ? toast("Paper session stopped") : toast(data.error || "Unable to stop paper session", true);
  if (ok) {
    renderRunDetail(data);
    renderPaperSession(null);
  }
  await refreshAll();
}

async function logPaperSignal(event) {
  event.preventDefault();
  const payload = collectFormData(event.target);
  const { ok, data } = await api("POST", "/api/paper/signal", payload);
  ok ? toast(`Signal logged${data.symbol ? ` for ${data.symbol}` : ""}`) : toast(data.error || "Unable to log signal", true);
  if (ok) event.target.reset();
  await refreshAll();
}

async function logPaperTrade(event) {
  event.preventDefault();
  const payload = collectFormData(event.target);
  const { ok, data } = await api("POST", "/api/paper/trade", payload);
  ok ? toast(`Trade logged${data.symbol ? ` for ${data.symbol}` : ""}`) : toast(data.error || "Unable to log trade", true);
  if (ok) event.target.reset();
  await refreshAll();
}

function runCardMarkup(run, options = {}) {
  const metrics = run.metrics || {};
  const checked = viewState.compareIds.has(run.id) ? "checked" : "";
  return `
    <article class="run-card ${options.compact ? "compact-card" : ""}">
      <div class="run-card-top">
        <div>
          <p class="eyebrow">${run.run_type}</p>
          <h3>${run.title}</h3>
        </div>
        <label class="compare-toggle">
          <input type="checkbox" data-compare-id="${run.id}" ${checked} />
          Compare
        </label>
      </div>
      <div class="summary-grid">
        <div><span class="info-label">Status</span><strong>${run.status}</strong></div>
        <div><span class="info-label">Trades</span><strong>${fmtNumber(run.trade_count)}</strong></div>
        <div><span class="info-label">Events</span><strong>${fmtNumber(run.event_count)}</strong></div>
        <div><span class="info-label">Net PnL</span><strong>${metrics.net_pnl !== undefined ? fmtCurrency(metrics.net_pnl) : "—"}</strong></div>
      </div>
      <button class="btn btn-secondary compact" type="button" data-run-id="${run.id}">Open</button>
    </article>
  `;
}

function renderRunCards(container, runs, options = {}) {
  if (!runs || !runs.length) {
    container.className = "list-stack empty-state";
    container.textContent = "No runs yet.";
    return;
  }
  container.className = "list-stack";
  container.innerHTML = runs.map((run) => runCardMarkup(run, options)).join("");
}

async function loadRuns() {
  const type = document.getElementById("history-type").value;
  const status = document.getElementById("history-status").value;
  const query = new URLSearchParams();
  if (type) query.set("type", type);
  if (status) query.set("status", status);
  const { ok, data } = await api("GET", `/api/runs?${query.toString()}`);
  if (!ok) {
    toast(data.error || "Unable to load history", true);
    return;
  }
  renderRunCards(document.getElementById("history-list"), data);
}

function summaryList(summary) {
  const entries = Object.entries(summary || {});
  if (!entries.length) return "<p class='empty-state'>No summary recorded.</p>";
  return `<div class="summary-grid">${entries.map(([key, value]) => `
    <div><span class="info-label">${key.replaceAll("_", " ")}</span><strong>${typeof value === "number" ? fmtNumber(value) : value}</strong></div>
  `).join("")}</div>`;
}

function metricList(metrics) {
  const entries = Object.entries(metrics || {});
  if (!entries.length) return "<p class='empty-state'>No metrics recorded.</p>";
  return `<div class="summary-grid">${entries.map(([key, value]) => `
    <div><span class="info-label">${key.replaceAll("_", " ")}</span><strong>${typeof value === "number" && key.includes("pnl") ? fmtCurrency(value) : fmtNumber(value)}</strong></div>
  `).join("")}</div>`;
}

function tradeTable(trades) {
  if (!trades || !trades.length) return "<p class='empty-state'>No trades recorded.</p>";
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>#</th><th>Entry</th><th>Exit</th><th>Qty</th><th>Net</th><th>Reason</th></tr>
        </thead>
        <tbody>
          ${trades.slice(0, 25).map((trade) => `
            <tr>
              <td>${trade.sequence_no || "—"}</td>
              <td>${trade.entry_price !== undefined ? fmtNumber(trade.entry_price) : "—"}</td>
              <td>${trade.exit_price !== undefined ? fmtNumber(trade.exit_price) : "—"}</td>
              <td>${trade.quantity !== undefined ? fmtNumber(trade.quantity) : "—"}</td>
              <td>${trade.net_pnl !== undefined ? fmtCurrency(trade.net_pnl) : "—"}</td>
              <td>${trade.exit_reason || trade.note || "—"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function eventsList(events) {
  if (!events || !events.length) return "<p class='empty-state'>No events recorded.</p>";
  return `
    <ul class="timeline">
      ${events.slice(-15).reverse().map((event) => `
        <li>
          <strong>${event.event_type}</strong>
          <span>${fmtDate(event.timestamp)}</span>
          <pre>${prettifyJson(event.payload)}</pre>
        </li>
      `).join("")}
    </ul>
  `;
}

function runDetailMarkup(run) {
  return `
    <div class="detail-stack">
      <div class="detail-header">
        <div>
          <p class="eyebrow">${run.run_type} • ${run.status}</p>
          <h3>${run.title}</h3>
          <p class="muted-copy">${run.id}</p>
        </div>
      </div>
      <section>
        <h4>Summary</h4>
        ${summaryList(run.summary)}
      </section>
      <section>
        <h4>Metrics</h4>
        ${metricList(run.metrics)}
      </section>
      <section>
        <h4>Trades</h4>
        ${tradeTable(run.trades)}
      </section>
      <section>
        <h4>Events</h4>
        ${eventsList(run.events)}
      </section>
    </div>
  `;
}

function renderRunDetail(run) {
  const container = document.getElementById("run-detail");
  container.className = "";
  container.innerHTML = runDetailMarkup(run);
  const backtestResult = document.getElementById("backtest-result");
  backtestResult.className = "";
  backtestResult.innerHTML = runDetailMarkup(run);
}

async function openRun(runId) {
  const { ok, data } = await api("GET", `/api/runs/${runId}`);
  if (!ok) {
    toast(data.error || "Unable to load run", true);
    return;
  }
  viewState.selectedRunId = runId;
  renderRunDetail(data);
}

async function compareRuns() {
  if (viewState.compareIds.size < 2) {
    toast("Select at least two runs to compare", true);
    return;
  }
  const { ok, data } = await api("GET", `/api/runs/compare?ids=${encodeURIComponent([...viewState.compareIds].join(","))}`);
  if (!ok) {
    toast(data.error || "Unable to compare runs", true);
    return;
  }
  const container = document.getElementById("compare-detail");
  const metricRows = Object.entries(data.metrics).map(([key, entries]) => `
    <tr>
      <th>${key.replaceAll("_", " ")}</th>
      ${entries.map((entry) => `<td>${entry.value === null || entry.value === undefined ? "—" : fmtNumber(entry.value)}${entry.delta_vs_first === null || entry.delta_vs_first === undefined ? "" : `<div class="delta">${entry.delta_vs_first >= 0 ? "+" : ""}${fmtNumber(entry.delta_vs_first)}</div>`}</td>`).join("")}
    </tr>
  `).join("");
  container.className = "";
  container.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            ${data.runs.map((run) => `<th>${run.title}</th>`).join("")}
          </tr>
        </thead>
        <tbody>${metricRows}</tbody>
      </table>
    </div>
  `;
}

async function loadCurrentSettings() {
  const { ok, data } = await api("GET", "/api/settings");
  if (!ok) return;
  const form = document.getElementById("settings-form");
  form.reset();
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "object" && value !== null) {
      for (const [subkey, subval] of Object.entries(value)) {
        const input = form.elements[`${key}.${subkey}`];
        if (input) input.value = subval;
      }
    } else {
      const input = form.elements[key];
      if (input) input.value = value;
    }
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = nestDotKeys(collectFormData(event.target));
  const { ok, data } = await api("PUT", "/api/settings", payload);
  const msg = document.getElementById("settings-msg");
  msg.classList.remove("hidden", "error", "success");
  if (ok) {
    msg.textContent = "Settings saved";
    msg.classList.add("success");
    toast("Settings saved");
  } else {
    msg.textContent = (data.errors || [data.error || "Unable to save settings"]).join("; ");
    msg.classList.add("error");
    toast("Settings failed validation", true);
  }
  await refreshAll();
}

async function loadLogs() {
  const { ok, data } = await api("GET", "/api/logs?n=40");
  if (!ok) return;
  const list = document.getElementById("log-list");
  if (!data.length) {
    list.innerHTML = "<li class='empty-state'>No audit entries yet.</li>";
    return;
  }
  list.innerHTML = data.map((entry) => `
    <li class="log-item ${entry.result === "success" ? "ok" : entry.result === "noop" ? "noop" : "err"}">
      <div class="log-top"><strong>${entry.action}</strong><span>${fmtDate(entry.timestamp)}</span></div>
      <div>${entry.actor} • ${entry.result}</div>
      ${entry.detail ? `<div class="muted-copy">${entry.detail}</div>` : ""}
    </li>
  `).join("");
}

async function handleInstall() {
  if (!viewState.deferredInstallPrompt) {
    toast("Use your browser's Add to Home Screen option to install.", true);
    return;
  }
  viewState.deferredInstallPrompt.prompt();
  await viewState.deferredInstallPrompt.userChoice;
  viewState.deferredInstallPrompt = null;
  document.getElementById("btn-install").classList.add("hidden");
}

async function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    try {
      await navigator.serviceWorker.register("/sw.js");
    } catch {
      // ignore registration failures in unsupported environments
    }
  }
}

function wireEvents() {
  document.getElementById("btn-token").addEventListener("click", promptToken);
  document.getElementById("btn-install").addEventListener("click", handleInstall);
  document.getElementById("btn-start").addEventListener("click", () => botAction("start"));
  document.getElementById("btn-stop").addEventListener("click", () => botAction("stop"));
  document.getElementById("btn-mode-paper").addEventListener("click", () => setMode("paper"));
  document.getElementById("btn-mode-live").addEventListener("click", () => setMode("live"));
  document.getElementById("btn-killswitch").addEventListener("click", triggerKillSwitch);
  document.getElementById("btn-killswitch-reset").addEventListener("click", resetKillSwitch);
  document.getElementById("btn-refresh-dashboard").addEventListener("click", refreshApp);
  document.getElementById("btn-refresh-history").addEventListener("click", loadRuns);
  document.getElementById("btn-refresh-logs").addEventListener("click", loadLogs);
  document.getElementById("btn-compare-runs").addEventListener("click", compareRuns);
  document.getElementById("btn-paper-stop").addEventListener("click", stopPaperSession);
  document.getElementById("history-type").addEventListener("change", loadRuns);
  document.getElementById("history-status").addEventListener("change", loadRuns);
  document.getElementById("backtest-symbol").addEventListener("input", syncMarketSelection);
  document.getElementById("backtest-symbol").addEventListener("change", refreshMarketDataStatus);
  document.getElementById("backtest-exchange").addEventListener("change", refreshMarketDataStatus);
  document.getElementById("backtest-timeframe").addEventListener("change", refreshMarketDataStatus);

  document.getElementById("backtest-form").addEventListener("submit", submitBacktest);
  document.querySelectorAll("[data-date-preset]").forEach((button) => {
    button.addEventListener("click", () => applyDatePreset(button.dataset.datePreset));
  });
  document.getElementById("paper-start-form").addEventListener("submit", startPaperSession);
  document.getElementById("paper-signal-form").addEventListener("submit", logPaperSignal);
  document.getElementById("paper-trade-form").addEventListener("submit", logPaperTrade);
  document.getElementById("settings-form").addEventListener("submit", saveSettings);

  document.querySelectorAll(".tabbar-btn").forEach((button) => {
    button.addEventListener("click", () => showScreen(button.dataset.screen));
  });

  document.getElementById("history-list").addEventListener("click", async (event) => {
    const runButton = event.target.closest("[data-run-id]");
    if (runButton) await openRun(runButton.dataset.runId);
  });
  document.getElementById("dashboard-runs").addEventListener("click", async (event) => {
    const runButton = event.target.closest("[data-run-id]");
    if (runButton) {
      showScreen("history");
      await openRun(runButton.dataset.runId);
    }
  });

  document.addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-compare-id]");
    if (!checkbox) return;
    if (checkbox.checked) viewState.compareIds.add(checkbox.dataset.compareId);
    else viewState.compareIds.delete(checkbox.dataset.compareId);
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    viewState.deferredInstallPrompt = event;
    document.getElementById("btn-install").classList.remove("hidden");
  });
}

(async function init() {
  wireEvents();
  renderTokenStatus();
  await registerServiceWorker();
  await refreshAll();
  setInterval(refreshStatusOnly, 15000);
})();
