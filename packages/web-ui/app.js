const config = window.__DAARI_WEB_UI_CONFIG__ || {};
const apiBaseUrl = (config.apiBaseUrl || "http://127.0.0.1:11435").replace(/\/$/, "");

const totalNode = document.getElementById("total-requests");
const errorsNode = document.getElementById("errors");
const tiersNode = document.getElementById("tiers-table");
const orgNode = document.getElementById("org-learning");
const statusNode = document.getElementById("status");
const refreshButton = document.getElementById("refresh");

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
    return;
  }
  for (const [tier, details] of entries.sort(([a], [b]) => a.localeCompare(b))) {
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

refreshButton.addEventListener("click", loadStats);
loadStats();
