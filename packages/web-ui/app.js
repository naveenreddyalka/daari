const config = window.__DAARI_WEB_UI_CONFIG__ || {};
const apiBaseUrl = (config.apiBaseUrl || "http://127.0.0.1:11435").replace(/\/$/, "");

const totalNode = document.getElementById("total-requests");
const errorsNode = document.getElementById("errors");
const tiersNode = document.getElementById("tiers-table");
const tiersChartNode = document.getElementById("tiers-chart");
const orgNode = document.getElementById("org-learning");
const orgSummaryNode = document.getElementById("org-summary");
const statusNode = document.getElementById("status");
const refreshButton = document.getElementById("refresh");
const exportButton = document.getElementById("export-stats");
const themeToggleButton = document.getElementById("theme-toggle");
const autoRefreshNode = document.getElementById("auto-refresh");
const refreshIntervalNode = document.getElementById("refresh-interval");
const THEME_KEY = "daari.webui.theme";
let refreshTimerId = null;
let latestStats = null;
let latestOrgProfile = null;

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
  tiersNode.innerHTML = "";
  const entries = Object.entries(tiers || {});
  if (entries.length === 0) {
    tiersNode.innerHTML = '<tr><td colspan="4">No tier data yet.</td></tr>';
    tiersChartNode.innerHTML = "";
    return;
  }
  const sorted = entries.sort(([a], [b]) => a.localeCompare(b));
  const maxCount = Math.max(
    ...sorted.map(([, details]) => (typeof details?.count === "number" ? details.count : 0)),
    1
  );
  tiersChartNode.innerHTML = "";
  for (const [tier, details] of sorted) {
    const count = typeof details?.count === "number" ? details.count : 0;
    const width = Math.max(2, Math.round((count / maxCount) * 100));
    const row = document.createElement("div");
    row.className = "tier-bar-row";
    row.innerHTML = `
      <span>${tier}</span>
      <div class="tier-track"><div class="tier-fill" style="width: ${width}%"></div></div>
      <span class="tier-count">${formatNumber(count)}</span>
    `;
    tiersChartNode.appendChild(row);
  }
  for (const [tier, details] of sorted) {
    const row = document.createElement("tr");
    const count = typeof details?.count === "number" ? details.count : 0;
    const p50 = typeof details?.p50_ms === "number" ? details.p50_ms : null;
    const p95 = typeof details?.p95_ms === "number" ? details.p95_ms : null;
    row.innerHTML = `<td>${tier}</td><td>${formatNumber(count)}</td><td>${formatMs(p50)}</td><td>${formatMs(
      p95
    )}</td>`;
    tiersNode.appendChild(row);
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadStats() {
  statusNode.textContent = "Refreshing...";
  try {
    const stats = await fetchJson(`${apiBaseUrl}/v1/daari/stats`);
    latestStats = stats;
    totalNode.textContent = formatNumber(stats.total_requests);
    errorsNode.textContent = formatNumber(stats.errors);
    renderTiers(stats.tiers || {});

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
  } catch (error) {
    latestStats = null;
    latestOrgProfile = null;
    totalNode.textContent = "-";
    errorsNode.textContent = "-";
    renderTiers({});
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
exportButton.addEventListener("click", exportStats);
themeToggleButton.addEventListener("click", toggleTheme);
autoRefreshNode.addEventListener("change", configureAutoRefresh);
refreshIntervalNode.addEventListener("change", configureAutoRefresh);
window.addEventListener("beforeunload", clearAutoRefresh);
configureTheme();
configureAutoRefresh();
loadStats();
