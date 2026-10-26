const config = window.__DAARI_WEB_UI_CONFIG__ || {};
const apiBaseUrl = (config.apiBaseUrl || "http://127.0.0.1:11435").replace(/\/$/, "");

const totalNode = document.getElementById("total-requests");
const errorsNode = document.getElementById("errors");
const compactTokensDroppedNode = document.getElementById("compact-to-fit-tokens-dropped");
const mcpGrantDeniedNode = document.getElementById("mcp-grant-denied");
const tiersNode = document.getElementById("tiers-table");
const tiersChartNode = document.getElementById("tiers-chart");
const softWarningsNode = document.getElementById("soft-warnings-table");
const rejectsNode = document.getElementById("rejects-table");
const errorsByStatusNode = document.getElementById("errors-by-status-table");
const mcpToolCallsNode = document.getElementById("mcp-tool-calls-table");
const mcpTasksNode = document.getElementById("mcp-tasks-table");
const mcpTasksSummaryNode = document.getElementById("mcp-tasks-summary");
const teamRateLimitsNode = document.getElementById("team-rate-limits-table");
const keyRateLimitsNode = document.getElementById("key-rate-limits-table");
const backendsNode = document.getElementById("backends-table");
const backendSummaryTotalNode = document.getElementById("backend-summary-total");
const backendSummaryHealthyNode = document.getElementById("backend-summary-healthy");
const backendSummaryUnhealthyNode = document.getElementById("backend-summary-unhealthy");
const backendSummaryOpenCircuitNode = document.getElementById("backend-summary-open-circuit");
const systemoneBreakerStatusNode = document.getElementById("systemone-breaker-status");
const systemoneBreakerResetButton = document.getElementById("systemone-breaker-reset");
const systemoneBreakerResetStatusNode = document.getElementById("systemone-breaker-reset-status");
const fleetBreakersListNode = document.getElementById("fleet-breakers-list");
const fleetBreakersStatusNode = document.getElementById("fleet-breakers-status");
const orgNode = document.getElementById("org-learning");
const orgSummaryNode = document.getElementById("org-summary");
const statusNode = document.getElementById("status");
const schemaOkBannerNode = document.getElementById("schema-ok-banner");
const refreshButton = document.getElementById("refresh");
const exportButton = document.getElementById("export-stats");
const themeToggleButton = document.getElementById("theme-toggle");
const autoRefreshNode = document.getElementById("auto-refresh");
const refreshIntervalNode = document.getElementById("refresh-interval");
const reportDaysNode = document.getElementById("report-days");
const reportRequestsNode = document.getElementById("report-requests");
const reportHitRateNode = document.getElementById("report-hit-rate");
const reportLocalNode = document.getElementById("report-local");
const reportSavingsNode = document.getElementById("report-savings");
const reportTableNode = document.getElementById("report-table");
const reportTeamsTableNode = document.getElementById("report-teams-table");
const reportModelGroupSpendTableNode = document.getElementById("report-model-group-spend-table");
const spendExportSinceNode = document.getElementById("spend-export-since");
const spendExportFormatNode = document.getElementById("spend-export-format");
const spendExportModelNode = document.getElementById("spend-export-model");
const spendExportUsageSpeedNode = document.getElementById("spend-export-usage-speed");
const spendExportTeamNode = document.getElementById("spend-export-team");
const spendExportUntilNode = document.getElementById("spend-export-until");
const spendExportDownloadButton = document.getElementById("spend-export-download");
const spendExportStatusNode = document.getElementById("spend-export-status");
const cacheTrustTableNode = document.getElementById("cache-trust-table");
const reportStatusNode = document.getElementById("report-status");
const adminKeysTableNode = document.getElementById("admin-keys-table");
const adminKeysStatusNode = document.getElementById("admin-keys-status");
const adminKeysStatusFilterNode = document.getElementById("admin-keys-status-filter");
const adminKeysIdleDaysNode = document.getElementById("admin-keys-idle-days");
const adminTeamsTableNode = document.getElementById("admin-teams-table");
const adminTeamsStatusNode = document.getElementById("admin-teams-status");
const lockoutsTableNode = document.getElementById("lockouts-table");
const lockoutsStatusNode = document.getElementById("lockouts-status");
const enforcementTableNode = document.getElementById("enforcement-table");
const enforcementStatusNode = document.getElementById("enforcement-status");
const cacheInvalidateModelNode = document.getElementById("cache-invalidate-model");
const cacheInvalidateTeamNode = document.getElementById("cache-invalidate-team");
const cacheInvalidateKeyNode = document.getElementById("cache-invalidate-key");
const cacheInvalidateSubmitButton = document.getElementById("cache-invalidate-submit");
const cacheInvalidateStatusNode = document.getElementById("cache-invalidate-status");
const eventsTableNode = document.getElementById("events-table");
const eventsStatusNode = document.getElementById("events-status");
const eventsTeamFilterNode = document.getElementById("events-team-filter");
const eventsKeyFilterNode = document.getElementById("events-key-filter");
const eventsKindFilterNode = document.getElementById("events-kind-filter");
const eventsSinceFilterNode = document.getElementById("events-since-filter");
const eventsUntilFilterNode = document.getElementById("events-until-filter");
const eventsNextButton = document.getElementById("events-next");
const tracesTableNode = document.getElementById("traces-table");
const traceDetailNode = document.getElementById("trace-detail");
const tracesStatusNode = document.getElementById("traces-status");
const THEME_KEY = "daari.webui.theme";
const API_KEY_STORAGE = "daari.webui.apiKey";
let eventsCursor = "";
let refreshTimerId = null;
let latestStats = null;
let latestOrgProfile = null;
/** In-memory key when "remember for this session" is off. */
let memoryApiKey = "";

function clearNode(node) {
  if (!node) {
    return;
  }
  node.replaceChildren();
}

function appendTextCells(row, values, classNames = []) {
  values.forEach((value, index) => {
    const td = document.createElement("td");
    td.textContent = value == null ? "" : String(value);
    if (classNames[index]) {
      td.className = classNames[index];
    }
    row.appendChild(td);
  });
}

function setEmptyRow(tbody, colspan, message) {
  clearNode(tbody);
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = colspan;
  td.textContent = message;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

function getRememberApiKey() {
  const checkbox = document.getElementById("remember-api-key");
  return Boolean(checkbox && checkbox.checked);
}

function getApiKey() {
  const input = document.getElementById("api-key");
  if (input && typeof input.value === "string" && input.value.trim()) {
    return input.value.trim();
  }
  if (memoryApiKey) {
    return memoryApiKey;
  }
  try {
    return (sessionStorage.getItem(API_KEY_STORAGE) || "").trim();
  } catch {
    return "";
  }
}

function persistApiKey(value) {
  const trimmed = (value || "").trim();
  memoryApiKey = trimmed;
  // Never persist secrets in localStorage (survives XSS / shared profiles).
  try {
    localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    /* private mode */
  }
  try {
    if (getRememberApiKey() && trimmed) {
      sessionStorage.setItem(API_KEY_STORAGE, trimmed);
    } else {
      sessionStorage.removeItem(API_KEY_STORAGE);
    }
  } catch {
    /* private mode */
  }
}

function authHeaders(extra = {}) {
  const headers = { Accept: "application/json", ...extra };
  const key = getApiKey();
  if (key) {
    headers.Authorization = `Bearer ${key}`;
  }
  return headers;
}

function formatNumber(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toLocaleString();
}

function formatMs(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(1);
}

function renderTiers(tiers) {
  clearNode(tiersNode);
  clearNode(tiersChartNode);
  const entries = Object.entries(tiers || {});
  if (entries.length === 0) {
    setEmptyRow(tiersNode, 4, "No tier data yet.");
    return;
  }
  const sorted = entries.sort(([a], [b]) => a.localeCompare(b));
  const maxCount = Math.max(
    ...sorted.map(([, details]) => (typeof details?.count === "number" ? details.count : 0)),
    1
  );
  for (const [tier, details] of sorted) {
    const count = typeof details?.count === "number" ? details.count : 0;
    const width = Math.max(2, Math.round((count / maxCount) * 100));
    const row = document.createElement("div");
    row.className = "tier-bar-row";
    const label = document.createElement("span");
    label.textContent = String(tier);
    const track = document.createElement("div");
    track.className = "tier-track";
    const fill = document.createElement("div");
    fill.className = "tier-fill";
    fill.style.width = `${width}%`;
    track.appendChild(fill);
    const countSpan = document.createElement("span");
    countSpan.className = "tier-count";
    countSpan.textContent = formatNumber(count);
    row.appendChild(label);
    row.appendChild(track);
    row.appendChild(countSpan);
    tiersChartNode.appendChild(row);
  }
  for (const [tier, details] of sorted) {
    const row = document.createElement("tr");
    const count = typeof details?.count === "number" ? details.count : 0;
    const p50 = typeof details?.p50_ms === "number" ? details.p50_ms : null;
    const p95 = typeof details?.p95_ms === "number" ? details.p95_ms : null;
    appendTextCells(row, [tier, formatNumber(count), formatMs(p50), formatMs(p95)]);
    tiersNode.appendChild(row);
  }
}

function renderKindCounts(tbody, counts, emptyLabel) {
  if (!tbody) {
    return;
  }
  const entries = Object.entries(counts || {}).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    setEmptyRow(tbody, 2, emptyLabel);
    return;
  }
  clearNode(tbody);
  for (const [kind, count] of entries) {
    const row = document.createElement("tr");
    appendTextCells(row, [kind, formatNumber(typeof count === "number" ? count : 0)]);
    tbody.appendChild(row);
  }
}

function renderMcpStats(toolCalls, tasks) {
  renderKindCounts(mcpToolCallsNode, toolCalls || {}, "No MCP tool calls yet.");
  const statusCounts = { ...(tasks || {}) };
  const active = statusCounts.active;
  const total = statusCounts.total;
  delete statusCounts.active;
  delete statusCounts.total;
  renderKindCounts(mcpTasksNode, statusCounts, "No MCP tasks tracked.");
  if (mcpTasksSummaryNode) {
    const activeText = typeof active === "number" ? formatNumber(active) : "-";
    const totalText = typeof total === "number" ? formatNumber(total) : "-";
    mcpTasksSummaryNode.textContent = `Active tasks: ${activeText} (total tracked: ${totalText})`;
  }
}

function renderBackendSummary(summary) {
  const counts = summary && typeof summary === "object" ? summary : {};
  const set = (node, key) => {
    if (!node) {
      return;
    }
    const value = counts[key];
    node.textContent = formatNumber(typeof value === "number" ? value : 0);
  };
  set(backendSummaryTotalNode, "total");
  set(backendSummaryHealthyNode, "healthy");
  set(backendSummaryUnhealthyNode, "unhealthy");
  set(backendSummaryOpenCircuitNode, "open_circuit");
  if (backendSummaryOpenCircuitNode) {
    const open = counts.open_circuit;
    backendSummaryOpenCircuitNode.classList.toggle(
      "metric-warn",
      typeof open === "number" && open > 0
    );
  }
}

function renderSystemoneBreaker(rows) {
  if (!systemoneBreakerStatusNode) {
    return;
  }
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) {
    systemoneBreakerStatusNode.textContent = "Systemone breaker: closed (no trips yet).";
    systemoneBreakerStatusNode.classList.remove("metric-warn");
    return;
  }
  const parts = list.map((row) => {
    const base = row && row.base ? String(row.base) : "systemone";
    const state = row && row.state ? String(row.state) : "closed";
    const rejects = typeof row?.rejects === "number" ? row.rejects : 0;
    return `${base}=${state} (rejects ${rejects})`;
  });
  systemoneBreakerStatusNode.textContent = `Systemone breaker: ${parts.join("; ")}`;
  const anyOpen = list.some((row) => String(row?.state || "") === "open");
  systemoneBreakerStatusNode.classList.toggle("metric-warn", anyOpen);
}

function renderFleetBreakers(rows) {
  if (!fleetBreakersListNode) {
    return;
  }
  clearNode(fleetBreakersListNode);
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No breaker trips yet.";
    fleetBreakersListNode.appendChild(empty);
    return;
  }
  for (const row of list) {
    const family = row && row.family ? String(row.family) : "unknown";
    const target = row && row.target ? String(row.target) : "-";
    const state = row && row.state ? String(row.state) : "closed";
    const li = document.createElement("li");
    li.style.marginBottom = "0.25rem";
    const label = document.createElement("span");
    label.textContent = `${family}:${target} = ${state}`;
    if (state === "open") {
      label.classList.add("metric-warn");
    }
    li.appendChild(label);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Reset";
    btn.style.marginLeft = "0.5rem";
    btn.dataset.family = family;
    btn.dataset.target = target;
    btn.addEventListener("click", () => resetFleetBreaker(family, target));
    li.appendChild(btn);
    fleetBreakersListNode.appendChild(li);
  }
}

async function resetFleetBreaker(family, target) {
  if (!fleetBreakersStatusNode) {
    return;
  }
  fleetBreakersStatusNode.textContent = `Resetting ${family}:${target}…`;
  try {
    const response = await fetch(`${apiBaseUrl}/v1/daari/breakers/reset`, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ family, target }),
    });
    if (response.status === 403) {
      fleetBreakersStatusNode.textContent =
        "403 Forbidden — breaker reset requires an admin API key.";
      return;
    }
    if (!response.ok) {
      fleetBreakersStatusNode.textContent = `Breaker reset failed: ${response.status}`;
      return;
    }
    const payload = await response.json();
    if (Array.isArray(payload.breakers)) {
      renderFleetBreakers(payload.breakers);
    } else {
      await loadStats();
    }
    fleetBreakersStatusNode.textContent = `Reset ${family}:${target}.`;
  } catch (error) {
    fleetBreakersStatusNode.textContent = `Breaker reset failed: ${error.message}`;
  }
}

function renderBackends(backends) {
  if (!backendsNode) {
    return;
  }
  const rows = Array.isArray(backends) ? backends : [];
  if (rows.length === 0) {
    setEmptyRow(backendsNode, 4, "No local pool backends.");
    return;
  }
  clearNode(backendsNode);
  const sorted = [...rows].sort((a, b) => String(a?.id || "").localeCompare(String(b?.id || "")));
  for (const backend of sorted) {
    const row = document.createElement("tr");
    const id = backend?.id != null ? String(backend.id) : "-";
    const healthy =
      typeof backend?.healthy === "boolean" ? (backend.healthy ? "yes" : "no") : "-";
    const circuit = backend?.circuit != null ? String(backend.circuit) : "-";
    const outstanding =
      typeof backend?.outstanding === "number" ? formatNumber(backend.outstanding) : "-";
    appendTextCells(row, [id, healthy, circuit, outstanding]);
    backendsNode.appendChild(row);
  }
}

function renderTeamRateLimits(rows) {
  if (!teamRateLimitsNode) {
    return;
  }
  const items = Array.isArray(rows) ? rows : [];
  if (items.length === 0) {
    setEmptyRow(teamRateLimitsNode, 4, "No team rate limits.");
    return;
  }
  clearNode(teamRateLimitsNode);
  for (const item of items) {
    const tr = document.createElement("tr");
    const team = item?.team != null ? String(item.team) : "-";
    const kind = item?.kind != null ? String(item.kind) : "-";
    const limit = item?.limit != null ? String(item.limit) : "-";
    const remaining = item?.remaining != null ? String(item.remaining) : "-";
    appendTextCells(tr, [team, kind, limit, remaining]);
    teamRateLimitsNode.appendChild(tr);
  }
}

function renderKeyRateLimits(rows) {
  if (!keyRateLimitsNode) {
    return;
  }
  const items = Array.isArray(rows) ? rows : [];
  if (items.length === 0) {
    setEmptyRow(keyRateLimitsNode, 4, "No key rate limits.");
    return;
  }
  clearNode(keyRateLimitsNode);
  for (const item of items) {
    const tr = document.createElement("tr");
    const key = item?.key != null ? String(item.key) : "-";
    const kind = item?.kind != null ? String(item.kind) : "-";
    const limit = item?.limit != null ? String(item.limit) : "-";
    const remaining = item?.remaining != null ? String(item.remaining) : "-";
    appendTextCells(tr, [key, kind, limit, remaining]);
    keyRateLimitsNode.appendChild(tr);
  }
}

async function fetchJson(url, init = {}) {
  const headers = authHeaders(init.headers || {});
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("401 Unauthorized — set API key / Bearer above");
    }
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function formatSpendSummary(spend) {
  if (!Array.isArray(spend) || spend.length === 0) {
    return "-";
  }
  return spend
    .map((entry) => {
      const quota = entry.quota === "requests" ? "req" : "$";
      if (quota === "req") {
        return `${entry.spend}/${entry.limit} req (${entry.window})`;
      }
      const spendVal = typeof entry.spend === "number" ? entry.spend.toFixed(2) : entry.spend;
      const limitVal = typeof entry.limit === "number" ? entry.limit.toFixed(2) : entry.limit;
      return `$${spendVal}/$${limitVal} (${entry.window})`;
    })
    .join("; ");
}

function renderReportTeams(teams) {
  if (!reportTeamsTableNode) {
    return;
  }
  const rows = Array.isArray(teams) ? teams : [];
  if (rows.length === 0) {
    setEmptyRow(reportTeamsTableNode, 4, "No team spend in this window.");
    return;
  }
  clearNode(reportTeamsTableNode);
  for (const team of rows) {
    const savings = team.estimated_saved_usd;
    const row = document.createElement("tr");
    appendTextCells(row, [
      team.team || "-",
      formatNumber(team.requests),
      formatNumber(team.cache_hits),
      typeof savings === "number" ? `$${savings.toFixed(4)}` : "-",
    ]);
    reportTeamsTableNode.appendChild(row);
  }
}

function renderModelGroupSpend(rows) {
  if (!reportModelGroupSpendTableNode) {
    return;
  }
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) {
    setEmptyRow(reportModelGroupSpendTableNode, 4, "No model-group spend recorded.");
    return;
  }
  clearNode(reportModelGroupSpendTableNode);
  for (const entry of list) {
    const spend = entry.spend_usd;
    const budget = entry.budget_usd;
    const row = document.createElement("tr");
    appendTextCells(row, [
      entry.model_group || "-",
      entry.window || "-",
      typeof spend === "number" ? `$${spend.toFixed(4)}` : "-",
      typeof budget === "number" && budget > 0 ? `$${budget.toFixed(4)}` : "-",
    ]);
    reportModelGroupSpendTableNode.appendChild(row);
  }
}

function renderAdminKeys(keys) {
  if (!adminKeysTableNode) {
    return;
  }
  const list = Array.isArray(keys) ? keys : [];
  if (list.length === 0) {
    setEmptyRow(adminKeysTableNode, 13, "No virtual keys.");
    return;
  }
  clearNode(adminKeysTableNode);
  for (const key of list) {
    const row = document.createElement("tr");
    appendTextCells(row, [
      key.key_id || "-",
      key.name || "-",
      key.team || key.team_id || "-",
      key.tier_cap || "-",
      key.expires_at || "never",
      key.last_used_at || "never",
      key.priority || "normal",
      key.cache_scope || "global",
      formatNumber(key.max_in_flight),
      formatNumber(key.user_rpd),
      formatNumber(key.user_daily_usd_cap),
      key.status || "-",
      formatSpendSummary(key.spend),
    ]);
    adminKeysTableNode.appendChild(row);
  }
}

function renderAdminTeams(teams) {
  if (!adminTeamsTableNode) {
    return;
  }
  const list = Array.isArray(teams) ? teams : [];
  if (list.length === 0) {
    setEmptyRow(adminTeamsTableNode, 9, "No teams.");
    return;
  }
  clearNode(adminTeamsTableNode);
  for (const team of list) {
    const row = document.createElement("tr");
    appendTextCells(row, [
      team.team_id || "-",
      team.name || "-",
      formatNumber(team.key_count),
      formatNumber(team.rpm),
      formatNumber(team.rpd),
      team.priority || "normal",
      team.cache_scope || "global",
      formatNumber(team.max_in_flight),
      formatSpendSummary(team.spend),
    ]);
    adminTeamsTableNode.appendChild(row);
  }
}

function renderReport(report) {
  const totals = report.totals || {};
  const requests = totals.requests || 0;
  const cacheHits = totals.cache_hits || 0;
  reportRequestsNode.textContent = formatNumber(requests);
  reportHitRateNode.textContent = requests > 0 ? `${((cacheHits / requests) * 100).toFixed(1)}%` : "-";
  reportLocalNode.textContent =
    requests > 0 ? `${(((totals.local_requests || 0) / requests) * 100).toFixed(1)}%` : "-";
  const savings = totals.estimated_saved_usd;
  reportSavingsNode.textContent = typeof savings === "number" ? `$${savings.toFixed(4)}` : "-";

  renderReportTeams(report.teams);
  renderModelGroupSpend(report.model_group_spend);

  const days = Array.isArray(report.days) ? [...report.days].reverse() : [];
  if (days.length === 0) {
    setEmptyRow(reportTableNode, 4, "No usage recorded in this window.");
    return;
  }
  clearNode(reportTableNode);
  for (const day of days) {
    const tierSummary = Object.entries(day.tiers || {})
      .map(([tier, stats]) => `${tier}:${formatNumber(stats.requests)}`)
      .join(" ");
    const row = document.createElement("tr");
    appendTextCells(
      row,
      [day.day, formatNumber(day.requests), formatNumber(day.cache_hits), tierSummary],
      ["", "", "", "tier-summary"]
    );
    reportTableNode.appendChild(row);
  }
}

function renderCacheTrust(trust) {
  const falseHits = (trust && trust.false_hit_rates) || {};
  const diversity = (trust && trust.diversity) || {};
  const categories = [...new Set([...Object.keys(falseHits), ...Object.keys(diversity)])].sort();
  if (categories.length === 0) {
    setEmptyRow(
      cacheTrustTableNode,
      4,
      "No shadow samples yet — cache trust data appears after L1 hits are sampled."
    );
    return;
  }
  clearNode(cacheTrustTableNode);
  for (const category of categories) {
    const shadow = falseHits[category];
    const div = diversity[category];
    const rate =
      shadow && typeof shadow.false_hit_rate === "number"
        ? `${(shadow.false_hit_rate * 100).toFixed(1)}%`
        : "-";
    const samples = shadow ? formatNumber(shadow.samples) : "-";
    const ratio =
      div && typeof div.ratio === "number"
        ? `${div.unique_answers}/${div.entries} (${(div.ratio * 100).toFixed(0)}%)`
        : "-";
    const row = document.createElement("tr");
    appendTextCells(row, [category, samples, rate, ratio]);
    cacheTrustTableNode.appendChild(row);
  }
}

async function loadReport() {
  const days = Number(reportDaysNode.value) || 7;
  try {
    const report = await fetchJson(`${apiBaseUrl}/v1/daari/report?days=${days}`);
    if (report.enabled === false) {
      reportStatusNode.textContent = "Usage ledger is disabled on the daemon.";
      renderReport({ totals: {}, days: [], teams: [], model_group_spend: [] });
      renderCacheTrust(report.cache_trust || null);
      return;
    }
    renderReport(report);
    renderCacheTrust(report.cache_trust || null);
    reportStatusNode.textContent = `Window: last ${days} days.`;
  } catch (error) {
    renderReport({ totals: {}, days: [], teams: [], model_group_spend: [] });
    renderCacheTrust(null);
    reportStatusNode.textContent = `Report unavailable (${error.message}).`;
  }
}

function adminKeysFilterParams() {
  const params = new URLSearchParams();
  const status =
    adminKeysStatusFilterNode && typeof adminKeysStatusFilterNode.value === "string"
      ? adminKeysStatusFilterNode.value.trim()
      : "";
  if (status) {
    params.set("status", status);
  }
  const idleRaw =
    adminKeysIdleDaysNode && typeof adminKeysIdleDaysNode.value === "string"
      ? adminKeysIdleDaysNode.value.trim()
      : "";
  if (idleRaw !== "") {
    const idle = Number(idleRaw);
    if (Number.isFinite(idle) && idle >= 0) {
      params.set("idle_days", String(Math.trunc(idle)));
    }
  }
  return params;
}

function adminKeysUrl() {
  const params = adminKeysFilterParams();
  const qs = params.toString();
  return qs ? `${apiBaseUrl}/v1/daari/keys?${qs}` : `${apiBaseUrl}/v1/daari/keys`;
}

function formatAdminKeysStatus(payload) {
  const count = Array.isArray(payload?.keys) ? payload.keys.length : 0;
  const params = adminKeysFilterParams();
  const status = params.get("status");
  const idle = params.get("idle_days");
  let noun = "key(s)";
  if (idle != null) {
    noun = "idle key(s)";
  } else if (status) {
    noun = `${status} key(s)`;
  }
  let text = `${count} ${noun}.`;
  if (payload && payload.has_more) {
    text += " More available.";
  }
  return text;
}

async function loadAdminKeys() {
  if (!adminKeysTableNode || !adminKeysStatusNode) {
    return;
  }
  try {
    const payload = await fetchJson(adminKeysUrl());
    renderAdminKeys(payload.keys);
    adminKeysStatusNode.textContent = formatAdminKeysStatus(payload);
  } catch (error) {
    renderAdminKeys([]);
    adminKeysStatusNode.textContent = `Keys unavailable (${error.message}).`;
  }
}

function eventsUrl() {
  const params = new URLSearchParams();
  params.set("limit", "20");
  const team =
    eventsTeamFilterNode && typeof eventsTeamFilterNode.value === "string"
      ? eventsTeamFilterNode.value.trim()
      : "";
  if (team) {
    params.set("team_id", team);
  }
  const keyId =
    eventsKeyFilterNode && typeof eventsKeyFilterNode.value === "string"
      ? eventsKeyFilterNode.value.trim()
      : "";
  if (keyId) {
    params.set("key_id", keyId);
  }
  const kind =
    eventsKindFilterNode && typeof eventsKindFilterNode.value === "string"
      ? eventsKindFilterNode.value.trim()
      : "";
  if (kind) {
    params.set("kind", kind);
  }
  const since =
    eventsSinceFilterNode && typeof eventsSinceFilterNode.value === "string"
      ? eventsSinceFilterNode.value.trim()
      : "";
  if (since) {
    params.set("since", since);
  }
  const until =
    eventsUntilFilterNode && typeof eventsUntilFilterNode.value === "string"
      ? eventsUntilFilterNode.value.trim()
      : "";
  if (until) {
    params.set("until", until);
  }
  if (eventsCursor) {
    params.set("cursor", eventsCursor);
  }
  return `${apiBaseUrl}/v1/daari/events?${params.toString()}`;
}

function renderEvents(events) {
  if (!eventsTableNode) {
    return;
  }
  const rows = Array.isArray(events) ? events : [];
  if (rows.length === 0) {
    setEmptyRow(eventsTableNode, 5, "No events recorded yet.");
    return;
  }
  clearNode(eventsTableNode);
  for (const event of rows) {
    const payload = event && typeof event.payload === "object" && event.payload ? event.payload : {};
    let payloadText = "{}";
    try {
      payloadText = JSON.stringify(payload);
    } catch {
      payloadText = "{}";
    }
    const row = document.createElement("tr");
    appendTextCells(row, [
      event && event.id != null ? event.id : "",
      (event && event.ts) || "-",
      (event && event.event) || "-",
      payload.team_id || "-",
      payloadText,
    ]);
    eventsTableNode.appendChild(row);
  }
}

async function loadEvents() {
  if (!eventsTableNode || !eventsStatusNode) {
    return;
  }
  try {
    const payload = await fetchJson(eventsUrl());
    renderEvents(payload.events);
    const next = payload && payload.next_cursor ? String(payload.next_cursor) : "";
    if (eventsNextButton) {
      eventsNextButton.dataset.cursor = next;
      eventsNextButton.disabled = !next;
    }
    const count = Array.isArray(payload.events) ? payload.events.length : 0;
    eventsStatusNode.textContent = payload.has_more
      ? `${count} event(s). More available.`
      : `${count} event(s).`;
  } catch (error) {
    renderEvents([]);
    if (eventsNextButton) {
      eventsNextButton.dataset.cursor = "";
      eventsNextButton.disabled = true;
    }
    eventsStatusNode.textContent = `Events unavailable (${error.message}).`;
  }
}

function renderLockouts(lockouts) {
  if (!lockoutsTableNode) {
    return;
  }
  const rows = Array.isArray(lockouts) ? lockouts : [];
  if (rows.length === 0) {
    setEmptyRow(lockoutsTableNode, 3, "No locked prefixes.");
    return;
  }
  clearNode(lockoutsTableNode);
  for (const entry of rows) {
    const row = document.createElement("tr");
    appendTextCells(row, [
      entry && entry.prefix != null ? entry.prefix : "",
      entry && entry.expires_in_seconds != null ? entry.expires_in_seconds : "",
    ]);
    const td = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lockout-unlock";
    button.textContent = "Unlock";
    button.dataset.prefix = entry && entry.prefix != null ? String(entry.prefix) : "";
    td.appendChild(button);
    row.appendChild(td);
    lockoutsTableNode.appendChild(row);
  }
}

async function loadLockouts() {
  if (!lockoutsTableNode || !lockoutsStatusNode) {
    return;
  }
  try {
    const payload = await fetchJson(`${apiBaseUrl}/v1/daari/lockouts`);
    const rows = Array.isArray(payload.lockouts) ? payload.lockouts : [];
    renderLockouts(rows);
    lockoutsStatusNode.textContent = `${rows.length} locked prefix(es).`;
  } catch (error) {
    renderLockouts([]);
    lockoutsStatusNode.textContent = `Lockouts unavailable (${error.message}).`;
  }
}

async function unlockPrefix(prefix) {
  if (!prefix || !lockoutsStatusNode) {
    return;
  }
  lockoutsStatusNode.textContent = "Unlocking…";
  try {
    await fetchJson(`${apiBaseUrl}/v1/daari/keys/unlock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prefix }),
    });
    await loadLockouts();
  } catch (error) {
    lockoutsStatusNode.textContent = `Unlock failed (${error.message}).`;
  }
}

function formatEnforcementActions(actions) {
  if (!Array.isArray(actions) || actions.length === 0) {
    return "—";
  }
  try {
    return JSON.stringify(actions);
  } catch {
    return String(actions.length);
  }
}

function renderEnforcement(profiles) {
  if (!enforcementTableNode) {
    return;
  }
  const rows = Array.isArray(profiles) ? profiles : [];
  if (rows.length === 0) {
    setEmptyRow(enforcementTableNode, 3, "No synced enforcement profiles.");
    return;
  }
  clearNode(enforcementTableNode);
  for (const entry of rows) {
    const row = document.createElement("tr");
    appendTextCells(row, [
      entry && entry.profile_id != null ? entry.profile_id : "",
      entry && entry.enforcement_status != null ? entry.enforcement_status : "",
      formatEnforcementActions(entry && entry.enforcement_actions),
    ]);
    enforcementTableNode.appendChild(row);
  }
}

async function loadEnforcement() {
  if (!enforcementTableNode || !enforcementStatusNode) {
    return;
  }
  try {
    const payload = await fetchJson(`${apiBaseUrl}/v1/daari/anthropic/enforcement`);
    const rows = Array.isArray(payload.profiles) ? payload.profiles : [];
    renderEnforcement(rows);
    const enforced =
      payload.enforced_count != null ? Number(payload.enforced_count) : rows.length;
    enforcementStatusNode.textContent = `${rows.length} profile(s); ${enforced} enforced.`;
  } catch (error) {
    renderEnforcement([]);
    enforcementStatusNode.textContent = `Enforcement unavailable (${error.message}).`;
  }
}

async function submitCacheInvalidate() {
  if (!cacheInvalidateStatusNode) {
    return;
  }
  const body = {};
  const model = cacheInvalidateModelNode && cacheInvalidateModelNode.value.trim();
  const teamId = cacheInvalidateTeamNode && cacheInvalidateTeamNode.value.trim();
  const keyId = cacheInvalidateKeyNode && cacheInvalidateKeyNode.value.trim();
  if (model) {
    body.model = model;
  }
  if (teamId) {
    body.team_id = teamId;
  }
  if (keyId) {
    body.key_id = keyId;
  }
  cacheInvalidateStatusNode.textContent = "Invalidating…";
  try {
    const payload = await fetchJson(`${apiBaseUrl}/v1/daari/cache/invalidate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const removed = payload.removed != null ? payload.removed : 0;
    const l0 = payload.l0_removed != null ? payload.l0_removed : 0;
    const l1 = payload.l1_removed != null ? payload.l1_removed : 0;
    cacheInvalidateStatusNode.textContent = `Removed ${removed} (L0 ${l0}, L1 ${l1}).`;
  } catch (error) {
    cacheInvalidateStatusNode.textContent = `Invalidate failed (${error.message}).`;
  }
}

async function loadAdminTeams() {
  if (!adminTeamsTableNode || !adminTeamsStatusNode) {
    return;
  }
  try {
    const payload = await fetchJson(`${apiBaseUrl}/v1/daari/teams`);
    renderAdminTeams(payload.teams);
    adminTeamsStatusNode.textContent = `${Array.isArray(payload.teams) ? payload.teams.length : 0} team(s).`;
  } catch (error) {
    renderAdminTeams([]);
    adminTeamsStatusNode.textContent = `Teams unavailable (${error.message}).`;
  }
}

function formatCompactToFitSummary(detail) {
  const steps = Array.isArray(detail?.steps) ? detail.steps : [];
  const lines = [];
  for (const step of steps) {
    if (!step || step.step !== "compact_to_fit") {
      continue;
    }
    const before = step.tokens_before;
    const after = step.tokens_after;
    if (typeof before !== "number" && typeof after !== "number") {
      continue;
    }
    lines.push(
      `compact_to_fit tokens_before=${typeof before === "number" ? before : "-"} tokens_after=${
        typeof after === "number" ? after : "-"
      }`
    );
  }
  return lines.join("\n");
}

function formatTraceDetail(detail) {
  const summary = formatCompactToFitSummary(detail);
  const json = JSON.stringify(detail, null, 2);
  return summary ? `${summary}\n\n${json}` : json;
}

async function showTraceDetail(traceId) {
  try {
    const detail = await fetchJson(`${apiBaseUrl}/v1/daari/traces/${encodeURIComponent(traceId)}`);
    traceDetailNode.hidden = false;
    traceDetailNode.textContent = formatTraceDetail(detail);
  } catch (error) {
    traceDetailNode.hidden = false;
    traceDetailNode.textContent = `Trace detail unavailable (${error.message}).`;
  }
}

async function loadTraces() {
  try {
    const payload = await fetchJson(`${apiBaseUrl}/v1/daari/traces?limit=10`);
    const traces = Array.isArray(payload.traces) ? payload.traces : [];
    if (traces.length === 0) {
      setEmptyRow(tracesTableNode, 4, "No traces recorded yet.");
      tracesStatusNode.textContent = "";
      return;
    }
    clearNode(tracesTableNode);
    for (const trace of traces) {
      const row = document.createElement("tr");
      const shortId = String(trace.trace_id || "").slice(0, 8);
      appendTextCells(row, [trace.ts || "-", trace.tier || "-", trace.category || "-"]);
      const td = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "trace-link";
      button.textContent = shortId;
      button.dataset.traceId = String(trace.trace_id || "");
      td.appendChild(button);
      row.appendChild(td);
      tracesTableNode.appendChild(row);
    }
    tracesStatusNode.textContent = "Click a trace id for the step timeline.";
  } catch (error) {
    clearNode(tracesTableNode);
    tracesStatusNode.textContent = `Traces unavailable (${error.message}).`;
  }
}

async function refreshSchemaOkBanner() {
  if (!schemaOkBannerNode) {
    return;
  }
  try {
    const headers = authHeaders({});
    const response = await fetch(`${apiBaseUrl}/ready`, { headers });
    let body = {};
    try {
      body = await response.json();
    } catch {
      body = {};
    }
    if (body && body.schema_ok === false) {
      schemaOkBannerNode.hidden = false;
      schemaOkBannerNode.textContent =
        "Local SQLite schema lag: /ready reports schema_ok false. Run migrations or restore matching store files before sending traffic.";
      return;
    }
    schemaOkBannerNode.hidden = true;
    schemaOkBannerNode.textContent = "";
  } catch {
    schemaOkBannerNode.hidden = true;
    schemaOkBannerNode.textContent = "";
  }
}

async function loadStats() {
  statusNode.textContent = "Refreshing...";
  void refreshSchemaOkBanner();
  try {
    const stats = await fetchJson(`${apiBaseUrl}/v1/daari/stats`);
    latestStats = stats;
    totalNode.textContent = formatNumber(stats.total_requests);
    errorsNode.textContent = formatNumber(stats.errors);
    if (compactTokensDroppedNode) {
      compactTokensDroppedNode.textContent = formatNumber(
        typeof stats.compact_to_fit_tokens_dropped === "number"
          ? stats.compact_to_fit_tokens_dropped
          : 0
      );
    }
    if (mcpGrantDeniedNode) {
      mcpGrantDeniedNode.textContent = formatNumber(
        typeof stats.mcp_grant_denied === "number" ? stats.mcp_grant_denied : 0
      );
    }
    renderTiers(stats.tiers || {});
    renderKindCounts(softWarningsNode, stats.soft_warnings, "No soft warnings yet.");
    renderKindCounts(rejectsNode, stats.rejects, "No hard rejects yet.");
    renderKindCounts(errorsByStatusNode, stats.errors_by_status, "No errors yet.");
    renderMcpStats(stats.mcp_tool_calls, stats.mcp_tasks);
    renderTeamRateLimits(stats.team_rate_limits);
    renderKeyRateLimits(stats.key_rate_limits);
    renderBackendSummary(stats.backend_summary);
    renderSystemoneBreaker(stats.systemone_breaker);
    renderFleetBreakers(stats.breakers);
    renderBackends(stats.backends);

    try {
      const profile = await fetchJson(`${apiBaseUrl}/v1/org-learning/profile`);
      latestOrgProfile = profile;
      const metrics = profile.metrics || {};
      const feedbackCount = typeof metrics.feedback_count === "number" ? metrics.feedback_count : 0;
      const cacheHitRate = typeof metrics.cache_hit_rate === "number" ? metrics.cache_hit_rate : null;
      orgSummaryNode.textContent =
        cacheHitRate === null
          ? `Org profile active. Feedback events: ${feedbackCount}.`
          : `Org profile active. Feedback events: ${feedbackCount}. Cache hit rate: ${(cacheHitRate * 100).toFixed(1)}%.`;
      orgNode.textContent = JSON.stringify(metrics, null, 2);
    } catch (_error) {
      latestOrgProfile = null;
      orgSummaryNode.textContent = "Not available (org-learning endpoint unreachable or unauthorized).";
      orgNode.textContent = "Not available (org-learning endpoint unreachable or unauthorized).";
    }

    statusNode.textContent = `Last refreshed: ${new Date().toLocaleTimeString()}`;
    void loadReport();
    void loadAdminKeys();
    void loadAdminTeams();
    void loadLockouts();
    void loadEnforcement();
    void loadEvents();
    void loadTraces();
  } catch (error) {
    latestStats = null;
    latestOrgProfile = null;
    totalNode.textContent = "-";
    errorsNode.textContent = "-";
    if (compactTokensDroppedNode) {
      compactTokensDroppedNode.textContent = "-";
    }
    if (mcpGrantDeniedNode) {
      mcpGrantDeniedNode.textContent = "-";
    }
    renderTiers({});
    renderKindCounts(softWarningsNode, {}, "No soft warnings yet.");
    renderKindCounts(rejectsNode, {}, "No hard rejects yet.");
    renderKindCounts(errorsByStatusNode, {}, "No errors yet.");
    renderMcpStats({}, {});
    renderTeamRateLimits([]);
    renderKeyRateLimits([]);
    renderBackends([]);
    renderLockouts([]);
    if (lockoutsStatusNode) {
      lockoutsStatusNode.textContent = "";
    }
    renderEnforcement([]);
    if (enforcementStatusNode) {
      enforcementStatusNode.textContent = "";
    }
    renderEvents([]);
    if (eventsStatusNode) {
      eventsStatusNode.textContent = "";
    }
    orgSummaryNode.textContent = "Not available";
    orgNode.textContent = "Not available";
    statusNode.textContent = `Could not reach ${apiBaseUrl}/v1/daari/stats (${error.message})`;
  }
}

function applyTheme(theme) {
  document.body.dataset.theme = theme;
  themeToggleButton.textContent = theme === "dark" ? "Switch to light" : "Switch to dark";
}

function configureTheme() {
  const stored = window.localStorage.getItem(THEME_KEY);
  applyTheme(stored === "light" ? "light" : "dark");
}

function toggleTheme() {
  const nextTheme = document.body.dataset.theme === "light" ? "dark" : "light";
  window.localStorage.setItem(THEME_KEY, nextTheme);
  applyTheme(nextTheme);
}

function exportStats() {
  if (!latestStats) {
    statusNode.textContent = "No stats loaded yet. Refresh first.";
    return;
  }
  const payload = {
    exported_at: new Date().toISOString(),
    api_base_url: apiBaseUrl,
    stats: latestStats,
    org_learning_profile: latestOrgProfile,
  };
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `daari-stats-${Date.now()}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function resetSystemoneBreaker() {
  if (!systemoneBreakerResetStatusNode) {
    return;
  }
  systemoneBreakerResetStatusNode.textContent = "Resetting systemone breaker…";
  try {
    const response = await fetch(`${apiBaseUrl}/v1/daari/systemone/breaker/reset`, {
      method: "POST",
      headers: authHeaders(),
    });
    if (response.status === 403) {
      systemoneBreakerResetStatusNode.textContent =
        "403 Forbidden — breaker reset requires an admin API key.";
      return;
    }
    if (!response.ok) {
      systemoneBreakerResetStatusNode.textContent = `Breaker reset failed: ${response.status}`;
      return;
    }
    const payload = await response.json();
    if (Array.isArray(payload.systemone_breaker)) {
      renderSystemoneBreaker(payload.systemone_breaker);
    } else {
      await loadStats();
    }
    systemoneBreakerResetStatusNode.textContent = "Breaker reset.";
  } catch (error) {
    systemoneBreakerResetStatusNode.textContent = `Breaker reset failed: ${error.message}`;
  }
}

async function downloadSpendExport() {
  if (!spendExportStatusNode || !spendExportDownloadButton) {
    return;
  }
  const since = (spendExportSinceNode && spendExportSinceNode.value) || "7d";
  const uiFormat = (spendExportFormatNode && spendExportFormatNode.value) || "csv";
  const model = (spendExportModelNode && spendExportModelNode.value.trim()) || "";
  const usageSpeed =
    (spendExportUsageSpeedNode && spendExportUsageSpeedNode.value.trim()) || "";
  const team = (spendExportTeamNode && spendExportTeamNode.value.trim()) || "";
  const until = (spendExportUntilNode && spendExportUntilNode.value.trim()) || "";
  const params = new URLSearchParams({ since });
  // HTTP accepts csv|json; jsonl is built client-side from the JSON page.
  params.set("format", uiFormat === "csv" ? "csv" : "json");
  if (model) {
    params.set("model", model);
  }
  if (usageSpeed) {
    params.set("usage_speed", usageSpeed);
  }
  if (team) {
    params.set("team", team);
  }
  if (until) {
    params.set("until", until);
  }
  const url = `${apiBaseUrl}/v1/daari/spend/export?${params.toString()}`;
  spendExportStatusNode.textContent = "Downloading spend export…";
  try {
    const response = await fetch(url, { headers: authHeaders() });
    if (response.status === 403) {
      spendExportStatusNode.textContent =
        "403 Forbidden — spend export requires an analyst (or admin) API key.";
      return;
    }
    if (!response.ok) {
      spendExportStatusNode.textContent = `Spend export failed: ${response.status}`;
      return;
    }
    let body;
    let filename;
    let mime;
    if (uiFormat === "csv") {
      body = await response.text();
      filename = `daari-spend-${since}.csv`;
      mime = "text/csv";
    } else {
      const payload = await response.json();
      const rows = Array.isArray(payload.rows) ? payload.rows : [];
      body = rows.map((row) => JSON.stringify(row)).join("\n");
      if (rows.length) {
        body += "\n";
      }
      filename = `daari-spend-${since}.jsonl`;
      mime = "application/x-ndjson";
    }
    triggerBlobDownload(new Blob([body], { type: mime }), filename);
    spendExportStatusNode.textContent = `Downloaded ${filename}`;
  } catch (error) {
    spendExportStatusNode.textContent = `Spend export failed: ${error.message}`;
  }
}

function clearAutoRefresh() {
  if (refreshTimerId !== null) {
    window.clearInterval(refreshTimerId);
    refreshTimerId = null;
  }
}

function configureAutoRefresh() {
  clearAutoRefresh();
  if (!autoRefreshNode.checked) {
    return;
  }
  const intervalMs = Number(refreshIntervalNode.value) || 5000;
  refreshTimerId = window.setInterval(() => {
    void loadStats();
  }, intervalMs);
}

refreshButton.addEventListener("click", loadStats);
reportDaysNode.addEventListener("change", loadReport);
if (adminKeysStatusFilterNode) {
  adminKeysStatusFilterNode.addEventListener("change", () => {
    void loadAdminKeys();
  });
}
if (adminKeysIdleDaysNode) {
  adminKeysIdleDaysNode.addEventListener("change", () => {
    void loadAdminKeys();
  });
}
function resetEventsCursorAndReload() {
  eventsCursor = "";
  void loadEvents();
}
if (eventsTeamFilterNode) {
  eventsTeamFilterNode.addEventListener("change", resetEventsCursorAndReload);
}
if (eventsKeyFilterNode) {
  eventsKeyFilterNode.addEventListener("change", resetEventsCursorAndReload);
}
if (eventsKindFilterNode) {
  eventsKindFilterNode.addEventListener("change", resetEventsCursorAndReload);
}
if (eventsSinceFilterNode) {
  eventsSinceFilterNode.addEventListener("change", resetEventsCursorAndReload);
}
if (eventsUntilFilterNode) {
  eventsUntilFilterNode.addEventListener("change", resetEventsCursorAndReload);
}
if (eventsNextButton) {
  eventsNextButton.addEventListener("click", () => {
    const next = eventsNextButton.dataset.cursor || "";
    if (!next) {
      return;
    }
    eventsCursor = next;
    void loadEvents();
  });
}
if (lockoutsTableNode) {
  lockoutsTableNode.addEventListener("click", (event) => {
    const target = event.target.closest("button.lockout-unlock");
    if (target) {
      void unlockPrefix(target.dataset.prefix || "");
    }
  });
}
if (cacheInvalidateSubmitButton) {
  cacheInvalidateSubmitButton.addEventListener("click", () => {
    void submitCacheInvalidate();
  });
}
tracesTableNode.addEventListener("click", (event) => {
  const target = event.target.closest("button.trace-link");
  if (target) {
    void showTraceDetail(target.dataset.traceId);
  }
});
exportButton.addEventListener("click", exportStats);
if (spendExportDownloadButton) {
  spendExportDownloadButton.addEventListener("click", () => {
    void downloadSpendExport();
  });
}
if (systemoneBreakerResetButton) {
  systemoneBreakerResetButton.addEventListener("click", () => {
    void resetSystemoneBreaker();
  });
}
themeToggleButton.addEventListener("click", toggleTheme);
autoRefreshNode.addEventListener("change", configureAutoRefresh);
refreshIntervalNode.addEventListener("change", configureAutoRefresh);
window.addEventListener("beforeunload", clearAutoRefresh);

const cfgConfidence = document.getElementById("cfg-confidence");
const cfgPrefer = document.getElementById("cfg-prefer");
const cfgDailyBudget = document.getElementById("cfg-daily-budget");
const cfgPersist = document.getElementById("cfg-persist");
const cfgLoad = document.getElementById("cfg-load");
const cfgSave = document.getElementById("cfg-save");
const cfgStatus = document.getElementById("cfg-status");

async function loadConfigEditor() {
  if (!cfgStatus) return;
  cfgStatus.textContent = "Loading config…";
  try {
    const response = await fetch(`${apiBaseUrl}/v1/daari/config`, {
      headers: authHeaders(),
    });
    if (response.status === 404) {
      cfgStatus.textContent = "Config editor disabled (set observability.config_editor=true).";
      return;
    }
    if (response.status === 401) {
      cfgStatus.textContent = "Load failed: 401 — set API key / Bearer above.";
      return;
    }
    if (!response.ok) {
      cfgStatus.textContent = `Load failed: HTTP ${response.status}`;
      return;
    }
    const body = await response.json();
    cfgConfidence.value = body.routing?.confidence_threshold ?? "";
    cfgPrefer.value = body.routing?.prefer || "balanced";
    cfgDailyBudget.value = body.frontier?.daily_budget_usd ?? "";
    cfgStatus.textContent = "Loaded.";
  } catch (err) {
    cfgStatus.textContent = `Load error: ${err}`;
  }
}

async function saveConfigEditor() {
  if (!cfgStatus) return;
  cfgStatus.textContent = "Saving…";
  const payload = {
    persist: Boolean(cfgPersist?.checked),
    routing: {
      confidence_threshold: Number(cfgConfidence.value),
      prefer: cfgPrefer.value,
    },
    frontier: {
      daily_budget_usd: Number(cfgDailyBudget.value),
    },
  };
  try {
    const response = await fetch(`${apiBaseUrl}/v1/daari/config`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (response.status === 401) {
      cfgStatus.textContent = "Save failed: 401 — set API key / Bearer above.";
      return;
    }
    if (!response.ok) {
      cfgStatus.textContent = `Save failed: HTTP ${response.status}`;
      return;
    }
    const body = await response.json();
    cfgStatus.textContent = body.persisted_to
      ? `Saved + persisted to ${body.persisted_to}`
      : "Saved (in-memory until restart).";
  } catch (err) {
    cfgStatus.textContent = `Save error: ${err}`;
  }
}

const apiKeyInput = document.getElementById("api-key");
const rememberApiKeyNode = document.getElementById("remember-api-key");
try {
  localStorage.removeItem(API_KEY_STORAGE);
} catch {
  /* ignore */
}
if (apiKeyInput) {
  try {
    const sessionKey = (sessionStorage.getItem(API_KEY_STORAGE) || "").trim();
    if (sessionKey) {
      apiKeyInput.value = sessionKey;
      memoryApiKey = sessionKey;
      if (rememberApiKeyNode) {
        rememberApiKeyNode.checked = true;
      }
    }
  } catch {
    /* ignore */
  }
  apiKeyInput.addEventListener("change", () => {
    persistApiKey(apiKeyInput.value);
  });
}
if (rememberApiKeyNode) {
  rememberApiKeyNode.addEventListener("change", () => {
    persistApiKey(apiKeyInput ? apiKeyInput.value : memoryApiKey);
  });
}

if (cfgLoad) cfgLoad.addEventListener("click", () => void loadConfigEditor());
if (cfgSave) cfgSave.addEventListener("click", () => void saveConfigEditor());

configureTheme();
configureAutoRefresh();
loadStats();
void loadConfigEditor();
