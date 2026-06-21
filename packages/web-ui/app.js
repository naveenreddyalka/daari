const config = window.__DAARI_WEB_UI_CONFIG__ || {};
const apiBaseUrl = (config.apiBaseUrl || "http://127.0.0.1:11435").replace(/\/$/, "");

const totalNode = document.getElementById("total-requests");
const errorsNode = document.getElementById("errors");
const tiersNode = document.getElementById("tiers-table");
const tiersChartNode = document.getElementById("tiers-chart");
const orgNode = document.getElementById("org-learning");
const statusNode = document.getElementById("status");
const refreshButton = document.getElementById("refresh");
const autoRefreshNode = document.getElementById("auto-refresh");
const refreshIntervalNode = document.getElementById("refresh-interval");
let refreshTimerId = null;

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
    totalNode.textContent = formatNumber(stats.total_requests);
    errorsNode.textContent = formatNumber(stats.errors);
    renderTiers(stats.tiers || {});

    try {
      const profile = await fetchJson(`${apiBaseUrl}/v1/org-learning/profile`);
      orgNode.textContent = JSON.stringify(profile.metrics || profile, null, 2);
    } catch (_error) {
      orgNode.textContent = "Not available (org-learning endpoint unreachable or unauthorized).";
    }

    statusNode.textContent = `Last refreshed: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    totalNode.textContent = "-";
    errorsNode.textContent = "-";
    renderTiers({});
    orgNode.textContent = "Not available";
    statusNode.textContent = `Could not reach ${apiBaseUrl}/v1/daari/stats (${error.message})`;
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
autoRefreshNode.addEventListener("change", configureAutoRefresh);
refreshIntervalNode.addEventListener("change", configureAutoRefresh);
window.addEventListener("beforeunload", clearAutoRefresh);
configureAutoRefresh();
loadStats();
