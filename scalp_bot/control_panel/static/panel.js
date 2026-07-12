/* scalp-bot control panel — frontend logic */
"use strict";

// ── Token management ──────────────────────────────────────────────
function getToken() {
  return localStorage.getItem("cp_token") || "";
}

function promptToken() {
  const t = window.prompt("Enter control panel token (leave blank to clear):", getToken());
  if (t === null) return; // cancelled
  if (t.trim() === "") {
    localStorage.removeItem("cp_token");
    toast("Token cleared");
  } else {
    localStorage.setItem("cp_token", t.trim());
    toast("Token saved");
  }
}

function authHeaders() {
  const token = getToken();
  const h = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = "Bearer " + token;
  return h;
}

// ── Generic fetch helper ──────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: authHeaders() };
  if (body !== undefined) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { error: "Network error: " + e.message } };
  }
}

// ── Toast ─────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, isErr) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  el.style.borderColor = isErr ? "var(--red)" : "var(--green)";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2800);
}

// ── Render status ─────────────────────────────────────────────────
function renderStatus(s) {
  const statusBadge = document.getElementById("status-badge");
  const modeBadge   = document.getElementById("mode-badge");
  const ksBadge     = document.getElementById("ks-badge");
  const ksReset     = document.getElementById("btn-ks-reset");

  if (s.running) {
    statusBadge.textContent = "Running";
    statusBadge.className   = "badge badge-running";
  } else {
    statusBadge.textContent = "Stopped";
    statusBadge.className   = "badge badge-stopped";
  }

  if (s.mode === "live") {
    modeBadge.textContent = "LIVE";
    modeBadge.className   = "badge badge-live";
  } else {
    modeBadge.textContent = "Paper";
    modeBadge.className   = "badge badge-paper";
  }

  if (s.kill_switch_active) {
    ksBadge.classList.remove("hidden");
    ksReset.classList.remove("hidden");
  } else {
    ksBadge.classList.add("hidden");
    ksReset.classList.add("hidden");
  }

  document.getElementById("started-at").textContent = s.started_at ? fmtDate(s.started_at) : "—";
  document.getElementById("stopped-at").textContent = s.stopped_at ? fmtDate(s.stopped_at) : "—";
  document.getElementById("last-signal").textContent = s.last_signal ? JSON.stringify(s.last_signal) : "—";
  document.getElementById("last-trade").textContent  = s.last_trade  ? JSON.stringify(s.last_trade)  : "—";
}

function fmtDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

// ── Poll status every 5 s ─────────────────────────────────────────
async function refreshStatus() {
  const { ok, data } = await api("GET", "/api/status");
  if (ok) renderStatus(data);
}
setInterval(refreshStatus, 5000);

// ── Bot actions ───────────────────────────────────────────────────
async function botAction(action) {
  const btn = document.getElementById("btn-" + action);
  if (btn) btn.disabled = true;
  const { ok, data } = await api("POST", "/api/" + action);
  if (ok) {
    renderStatus(data.status);
    toast(data.message || action + " OK");
  } else {
    toast((data.error || "Error") , true);
  }
  if (btn) btn.disabled = false;
  loadLogs();
}

async function triggerKillSwitch() {
  if (!confirm("Activate kill switch? This will stop the bot immediately.")) return;
  const { ok, data } = await api("POST", "/api/killswitch");
  if (ok) {
    renderStatus(data.status);
    toast("Kill switch activated", true);
  } else {
    toast(data.error || "Error", true);
  }
  loadLogs();
}

async function resetKillSwitch() {
  if (!confirm("Deactivate kill switch?")) return;
  const { ok, data } = await api("POST", "/api/killswitch/reset");
  if (ok) {
    renderStatus(data.status);
    toast("Kill switch deactivated");
  } else {
    toast(data.error || "Error", true);
  }
  loadLogs();
}

// ── Mode ──────────────────────────────────────────────────────────
async function setMode(mode) {
  const { ok, data } = await api("POST", "/api/mode/" + mode);
  if (ok) toast("Mode set to " + data.mode);
  else    toast(data.error || "Error", true);
  refreshStatus();
  loadLogs();
}

async function confirmLive() {
  const answer = window.prompt(
    '⚠ LIVE mode places REAL orders.\n\nType LIVE to confirm:',
    ""
  );
  if (answer !== "LIVE") { toast("Live mode not activated"); return; }
  const { ok, data } = await api("POST", "/api/mode/confirm-live", { confirm: "LIVE" });
  if (ok) toast("⚠ Switched to LIVE mode!");
  else    toast(data.error || "Error", true);
  refreshStatus();
  loadLogs();
}

// ── Settings ──────────────────────────────────────────────────────
function toggleSettings() {
  document.getElementById("settings-body").classList.toggle("hidden");
}

async function loadCurrentSettings() {
  const { ok, data } = await api("GET", "/api/settings");
  if (!ok) return;
  const form = document.getElementById("settings-form");
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "object" && value !== null) {
      for (const [subkey, subval] of Object.entries(value)) {
        const el = form.elements[key + "." + subkey];
        if (el) el.value = subval;
      }
    } else {
      const el = form.elements[key];
      if (el) el.value = value;
    }
  }
}

async function saveSettings(e) {
  e.preventDefault();
  const form = e.target;
  const flat = {};
  for (const el of form.elements) {
    if (!el.name || el.value === "") continue;
    flat[el.name] = el.type === "number" ? parseFloat(el.value) : el.value;
  }

  // Build nested object
  const nested = {};
  for (const [k, v] of Object.entries(flat)) {
    const parts = k.split(".");
    if (parts.length === 2) {
      nested[parts[0]] = nested[parts[0]] || {};
      nested[parts[0]][parts[1]] = v;
    } else {
      nested[k] = v;
    }
  }

  const msgEl = document.getElementById("settings-msg");
  const { ok, data } = await api("PUT", "/api/settings", nested);
  msgEl.classList.remove("hidden", "msg-ok", "msg-err");
  if (ok) {
    msgEl.textContent = "Settings saved.";
    msgEl.classList.add("msg-ok");
    toast("Settings saved");
  } else {
    const errs = data.errors ? data.errors.join("; ") : (data.error || "Error");
    msgEl.textContent = "Error: " + errs;
    msgEl.classList.add("msg-err");
    toast("Validation failed", true);
  }
  loadLogs();
}

// ── Logs ──────────────────────────────────────────────────────────
async function loadLogs() {
  const { ok, data } = await api("GET", "/api/logs?n=30");
  if (!ok) return;
  const ul = document.getElementById("log-list");
  ul.innerHTML = "";
  if (!data.length) {
    ul.innerHTML = "<li style='color:var(--muted)'>No entries yet.</li>";
    return;
  }
  for (const entry of data) {
    const li = document.createElement("li");
    const cls = entry.result === "success" ? "log-ok" :
                entry.result === "noop"    ? "log-noop" : "log-err";
    li.className = cls;
    const time = fmtDate(entry.timestamp);
    const detail = entry.detail ? ` — ${entry.detail}` : "";
    li.textContent = `${time}  ${entry.actor}  ${entry.action}  [${entry.result}]${detail}`;
    ul.appendChild(li);
  }
}

// ── Init ──────────────────────────────────────────────────────────
(async function init() {
  await refreshStatus();
  await loadCurrentSettings();
  await loadLogs();
})();
