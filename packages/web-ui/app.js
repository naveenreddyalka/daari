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
const orgNode = document.getElementById("org-learning");
const orgSummaryNode = document.getElementById("org-summary");
const statusNode = document.getElementById("status");
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
const cacheTrustTableNode = document.getElementById("cache-trust-table");
const reportStatusNode = document.getElementById("report-status");
const tracesTableNode = document.getElementById("traces-table");
const traceDetailNode = document.getElementById("trace-detail");
const tracesStatusNode = document.getElementById("traces-status");
const THEME_KEY = "daari.webui.theme";
const API_KEY_STORAGE = "daari.webui.apiKey";
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
      renderReport({ totals: {}, days: [] });
      renderCacheTrust(report.cache_trust || null);
      return;
    }
    renderReport(report);
    renderCacheTrust(report.cache_trust || null);
    reportStatusNode.textContent = `Window: last ${days} days.`;
  } catch (error) {
    renderReport({ totals: {}, days: [] });
    renderCacheTrust(null);
    reportStatusNode.textContent = `Report unavailable (${error.message}).`;
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

async function loadStats() {
  statusNode.textContent = "Refreshing...";
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
    renderMcpStats(stats.mcp_tool_calls, stats.mcp_tasks);
    renderTeamRateLimits(stats.team_rate_limits);
    renderKeyRateLimits(stats.key_rate_limits);
    renderBackendSummary(stats.backend_summary);
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
    renderMcpStats({}, {});
    renderTeamRateLimits([]);
    renderKeyRateLimits([]);
    renderBackends([]);
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
tracesTableNode.addEventListener("click", (event) => {
  const target = event.target.closest("button.trace-link");
  if (target) {
    void showTraceDetail(target.dataset.traceId);
  }
});
exportButton.addEventListener("click", exportStats);
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
