import assert from "node:assert/strict";
import { test } from "node:test";

import { fakeFetch, loadDashboard, settle } from "./harness.js";

const STATS = {
  total_requests: 42,
  errors: 1,
  compact_to_fit_tokens_dropped: 96,
  mcp_grant_denied: 3,
  tiers: { L0: { count: 10, p50_ms: 1, p95_ms: 2 }, L3: { count: 32, p50_ms: 900, p95_ms: 2100 } },
  soft_warnings: { rate_limit: 3, request_quota: 1 },
  rejects: { budget: 2, rate_limit: 4 },
  backends: [
    { id: "gpu-a", healthy: true, circuit: "closed", outstanding: 1 },
    { id: "gpu-b", healthy: false, circuit: "open", outstanding: 0 },
  ],
  backend_summary: { total: 2, healthy: 1, unhealthy: 1, open_circuit: 1 },
  mcp_tool_calls: { "route:ok": 5, "stats:deny": 2 },
  mcp_tasks: { working: 1, failed: 1, completed: 3, cancelled: 0, input_required: 0, active: 1, total: 5 },
  team_rate_limits: [
    { team: "eng", kind: "rpd", limit: 100, remaining: 40 },
    { team: "eng", kind: "rpm", limit: 10, remaining: 7 },
  ],
  key_rate_limits: [{ key: "alice", kind: "rpd", limit: 5, remaining: 4 }],
};

const REPORT = {
  enabled: true,
  days: [
    {
      day: "2026-07-10",
      requests: 30,
      cache_hits: 12,
      prompt_chars: 4000,
      completion_chars: 2000,
      tiers: { L0: { requests: 12, cache_hits: 12 }, L3: { requests: 18, cache_hits: 0 } },
    },
    {
      day: "2026-07-11",
      requests: 12,
      cache_hits: 6,
      prompt_chars: 1000,
      completion_chars: 500,
      tiers: { L0: { requests: 6, cache_hits: 6 }, L3: { requests: 6, cache_hits: 0 } },
    },
  ],
  totals: {
    requests: 42,
    cache_hits: 18,
    local_requests: 40,
    frontier_requests: 2,
    estimated_saved_usd: 0.0123,
  },
  cache_trust: {
    false_hit_rates: {
      doc_qa: { samples: 20, disagreements: 3, false_hit_rate: 0.15, avg_answer_similarity: 0.7 },
    },
    diversity: {
      doc_qa: { entries: 12, unique_answers: 4, ratio: 0.3333 },
      code_gen: { entries: 5, unique_answers: 5, ratio: 1.0 },
    },
  },
  teams: [
    { team: "eng", requests: 30, cache_hits: 12, estimated_saved_usd: 0.01 },
    { team: "ops", requests: 12, cache_hits: 6, estimated_saved_usd: 0.0023 },
  ],
  model_group_spend: [
    { model_group: "chat", window: "1d", spend_usd: 0.5, budget_usd: 10.0 },
    { model_group: "embed", window: "1d", spend_usd: 0.05, budget_usd: 0.0 },
  ],
};

const ADMIN_KEYS = {
  keys: [
    {
      key_id: "abc123",
      name: "alice",
      team: "eng",
      team_id: "t1",
      tier_cap: "L3",
      expires_at: "2099-01-01T00:00:00+00:00",
      status: "active",
      spend: [{ window: "day", quota: "usd", spend: 0.25, limit: 1.0 }],
    },
  ],
};

const ADMIN_TEAMS = {
  teams: [
    {
      team_id: "t1",
      name: "eng",
      key_count: 1,
      rpm: 60,
      rpd: 500,
      spend: [{ window: "day", quota: "usd", spend: 1.5, limit: 10.0 }],
    },
  ],
};

const TRACES = {
  traces: [
    { trace_id: "abcd1234efgh", ts: "2026-07-11T17:00:00Z", tier: "L3", category: "code_gen" },
    { trace_id: "zzzz9999yyyy", ts: "2026-07-11T16:59:00Z", tier: "L0", category: "doc_qa" },
  ],
};

const TRACE_DETAIL = {
  trace_id: "abcd1234efgh",
  tier: "L3",
  steps: [{ step: "profile" }, { step: "served", tier: "L3" }],
};

function routes(overrides = {}) {
  return {
    "/v1/daari/stats": STATS,
    "/v1/daari/report": REPORT,
    "/v1/daari/keys": ADMIN_KEYS,
    "/v1/daari/teams": ADMIN_TEAMS,
    "/v1/daari/traces/abcd1234efgh": TRACE_DETAIL,
    "/v1/daari/traces": TRACES,
    "/v1/org-learning/profile": { status: 404 },
    ...overrides,
  };
}

test("stats summary shows compact_to_fit_tokens_dropped and mcp_grant_denied", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.equal(doc.getElementById("compact-to-fit-tokens-dropped").textContent, "96");
  assert.equal(doc.getElementById("mcp-grant-denied").textContent, "3");
});

test("stats summary zeros compact/mcp counters when absent", async (t) => {
  const base = { ...STATS };
  delete base.compact_to_fit_tokens_dropped;
  delete base.mcp_grant_denied;
  const fetch = fakeFetch(routes({ "/v1/daari/stats": base }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.equal(doc.getElementById("compact-to-fit-tokens-dropped").textContent, "0");
  assert.equal(doc.getElementById("mcp-grant-denied").textContent, "0");
});

test("report totals and daily table render", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.equal(doc.getElementById("report-requests").textContent, "42");
  assert.equal(doc.getElementById("report-hit-rate").textContent, "42.9%");
  assert.equal(doc.getElementById("report-local").textContent, "95.2%");
  assert.equal(doc.getElementById("report-savings").textContent, "$0.0123");

  const rows = doc.querySelectorAll("#report-table tr");
  assert.equal(rows.length, 2);
  assert.match(rows[0].textContent, /2026-07-11/, "most recent day listed first");
  assert.match(rows[0].textContent, /L0:6/);
});

test("soft warnings and hard rejects tables render from stats", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const softRows = [...doc.querySelectorAll("#soft-warnings-table tr")];
  assert.equal(softRows.length, 2);
  assert.match(softRows[0].textContent, /rate_limit/);
  assert.match(softRows[0].textContent, /3/);
  assert.match(softRows[1].textContent, /request_quota/);
  const rejectRows = [...doc.querySelectorAll("#rejects-table tr")];
  assert.equal(rejectRows.length, 2);
  assert.match(rejectRows.map((r) => r.textContent).join("|"), /budget/);
  assert.match(rejectRows.map((r) => r.textContent).join("|"), /rate_limit/);
});

test("MCP tool outcomes and task counts render from stats", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const toolRows = [...doc.querySelectorAll("#mcp-tool-calls-table tr")];
  assert.equal(toolRows.length, 2);
  assert.match(toolRows.map((r) => r.textContent).join("|"), /route:ok/);
  assert.match(toolRows.map((r) => r.textContent).join("|"), /stats:deny/);
  const taskRows = [...doc.querySelectorAll("#mcp-tasks-table tr")];
  assert.match(taskRows.map((r) => r.textContent).join("|"), /working/);
  assert.match(taskRows.map((r) => r.textContent).join("|"), /failed/);
  assert.match(doc.getElementById("mcp-tasks-summary").textContent, /Active tasks: 1/);
});

test("team rate limits table includes rpd remaining", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll("#team-rate-limits-table tr")];
  assert.equal(rows.length, 2);
  const text = rows.map((r) => r.textContent).join("|");
  assert.match(text, /eng/);
  assert.match(text, /rpd/);
  assert.match(text, /100/);
  assert.match(text, /40/);
});

test("key rate limits table includes rpd remaining", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll("#key-rate-limits-table tr")];
  assert.equal(rows.length, 1);
  const text = rows.map((r) => r.textContent).join("|");
  assert.match(text, /alice/);
  assert.match(text, /rpd/);
  assert.match(text, /5/);
  assert.match(text, /4/);
});

test("tier table renders p50/p95 from stats payload", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll("#tiers-table tr")];
  assert.ok(rows.length >= 2);
  const text = rows.map((r) => r.textContent).join("|");
  assert.match(text, /L3/);
  assert.match(text, /900/);
  assert.match(text, /2100/);
  assert.doesNotMatch(text, /L3.*-\s*-/);
});

test("local pool backends table renders id/healthy/circuit/outstanding", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll("#backends-table tr")];
  assert.equal(rows.length, 2);
  const text = rows.map((r) => r.textContent).join("|");
  assert.match(text, /gpu-a/);
  assert.match(text, /closed/);
  assert.match(text, /gpu-b/);
  assert.match(text, /open/);
  assert.match(text, /yes/);
  assert.match(text, /no/);
});

test("backend_summary counts render near pool backends", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.equal(doc.getElementById("backend-summary-total").textContent, "2");
  assert.equal(doc.getElementById("backend-summary-healthy").textContent, "1");
  assert.equal(doc.getElementById("backend-summary-unhealthy").textContent, "1");
  assert.equal(doc.getElementById("backend-summary-open-circuit").textContent, "1");
  assert.ok(
    doc.getElementById("backend-summary-open-circuit").classList.contains("metric-warn"),
    "open_circuit > 0 should emphasize the metric"
  );
});

test("backend_summary zeros when pool empty", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/stats": {
        ...STATS,
        backends: [],
        backend_summary: { total: 0, healthy: 0, unhealthy: 0, open_circuit: 0 },
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.equal(doc.getElementById("backend-summary-total").textContent, "0");
  assert.equal(doc.getElementById("backend-summary-healthy").textContent, "0");
  assert.equal(doc.getElementById("backend-summary-unhealthy").textContent, "0");
  assert.equal(doc.getElementById("backend-summary-open-circuit").textContent, "0");
  assert.equal(
    doc.getElementById("backend-summary-open-circuit").classList.contains("metric-warn"),
    false,
    "open_circuit 0 stays neutral"
  );
});

test("empty backends shows clear empty state", async (t) => {
  const fetch = fakeFetch(routes({ "/v1/daari/stats": { ...STATS, backends: [] } }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = doc.querySelectorAll("#backends-table tr");
  assert.equal(rows.length, 1);
  assert.match(rows[0].textContent, /No local pool backends/);
});

test("cache trust panel shows false-hit rate and diversity per category", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll("#cache-trust-table tr")];
  assert.equal(rows.length, 2);
  const docQa = rows.find((row) => row.textContent.includes("doc_qa"));
  assert.match(docQa.textContent, /15\.0%/, "false-hit rate rendered");
  assert.match(docQa.textContent, /4\/12/, "diversity ratio rendered");
  const codeGen = rows.find((row) => row.textContent.includes("code_gen"));
  assert.match(codeGen.textContent, /5\/5/, "diversity without shadow samples still renders");
});

test("cache trust panel shows placeholder without data", async (t) => {
  const fetch = fakeFetch(
    routes({ "/v1/daari/report": { ...REPORT, cache_trust: { false_hit_rates: {}, diversity: {} } } })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = doc.querySelectorAll("#cache-trust-table tr");
  assert.match(rows[0].textContent, /No shadow samples yet/);
});

test("recent traces list renders and detail opens on click", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const links = doc.querySelectorAll("#traces-table button.trace-link");
  assert.equal(links.length, 2);
  assert.equal(links[0].textContent, "abcd1234");

  links[0].dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();

  const detail = doc.getElementById("trace-detail");
  assert.equal(detail.hidden, false);
  assert.match(detail.textContent, /"step": "served"/);
});

test("trace detail shows compact_to_fit tokens_before/tokens_after when step present", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/traces/abcd1234efgh": {
        trace_id: "abcd1234efgh",
        tier: "L6",
        steps: [
          { step: "profile" },
          {
            step: "compact_to_fit",
            tokens_before: 480,
            tokens_after: 120,
            messages_before: 40,
            messages_after: 8,
          },
          { step: "served", tier: "L6" },
        ],
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const link = doc.querySelector("#traces-table button.trace-link");
  link.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();

  const detail = doc.getElementById("trace-detail");
  assert.equal(detail.hidden, false);
  assert.match(detail.textContent, /compact_to_fit/);
  assert.match(detail.textContent, /tokens_before/);
  assert.match(detail.textContent, /tokens_after/);
  assert.match(detail.textContent, /480/);
  assert.match(detail.textContent, /120/);
});

test("disabled ledger shows a clear message", async (t) => {
  const fetch = fakeFetch(routes({ "/v1/daari/report": { enabled: false, days: [], totals: {} } }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.match(doc.getElementById("report-status").textContent, /ledger is disabled/);
  assert.equal(doc.getElementById("report-requests").textContent, "0");
});

test("report endpoint failure degrades gracefully", async (t) => {
  const fetch = fakeFetch(routes({ "/v1/daari/report": { status: 404 } }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.match(doc.getElementById("report-status").textContent, /Report unavailable/);
  const rows = doc.querySelectorAll("#report-table tr");
  assert.match(rows[0].textContent, /No usage recorded/);
});

test("empty traces show placeholder row", async (t) => {
  const fetch = fakeFetch(routes({ "/v1/daari/traces": { traces: [] } }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = doc.querySelectorAll("#traces-table tr");
  assert.match(rows[0].textContent, /No traces recorded yet/);
});

test("report window selector refetches with chosen days", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const selector = doc.getElementById("report-days");
  selector.value = "30";
  selector.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();

  assert.ok(
    fetch.calls.some((call) => call.url.includes("/v1/daari/report?days=30")),
    "changing the window must refetch with days=30"
  );
});

test("API key field sends Authorization Bearer on dashboard fetches", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const keyInput = doc.getElementById("api-key");
  assert.ok(keyInput, "api-key input must exist");
  keyInput.value = "sekret-key";
  keyInput.dispatchEvent(new dom.window.Event("change", { bubbles: true }));

  doc.getElementById("refresh").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();

  const statsCall = [...fetch.calls].reverse().find((c) => c.url.includes("/v1/daari/stats"));
  assert.ok(statsCall, "refresh must hit stats");
  assert.equal(statsCall.init?.headers?.Authorization, "Bearer sekret-key");
  // Default: memory only — never localStorage; sessionStorage only when opted in.
  assert.equal(dom.window.localStorage.getItem("daari.webui.apiKey"), null);
  assert.equal(dom.window.sessionStorage.getItem("daari.webui.apiKey"), null);
});

test("remember-for-session stores key in sessionStorage not localStorage", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const keyInput = doc.getElementById("api-key");
  const remember = doc.getElementById("remember-api-key");
  assert.ok(remember, "remember-api-key checkbox must exist");
  remember.checked = true;
  keyInput.value = "session-sekret";
  keyInput.dispatchEvent(new dom.window.Event("change", { bubbles: true }));

  assert.equal(dom.window.sessionStorage.getItem("daari.webui.apiKey"), "session-sekret");
  assert.equal(dom.window.localStorage.getItem("daari.webui.apiKey"), null);
});

test("malicious stats/trace fields render as inert text", async (t) => {
  const xss = '<img src=x onerror=window.__xss=1><script>window.__xss=1</script>';
  const fetch = fakeFetch(
    routes({
      "/v1/daari/stats": {
        ...STATS,
        tiers: { [xss]: { count: 1, p50_ms: 1, p95_ms: 2 } },
        soft_warnings: { [xss]: 1 },
        backends: [{ id: xss, healthy: true, circuit: xss, outstanding: 0 }],
        key_rate_limits: [{ key: xss, kind: "rpd", limit: 1, remaining: 1 }],
      },
      "/v1/daari/traces": {
        traces: [
          {
            trace_id: "safeid01abcdef",
            ts: xss,
            tier: xss,
            category: xss,
          },
        ],
      },
      "/v1/daari/keys": {
        keys: [
          {
            key_id: xss,
            name: xss,
            team: xss,
            tier_cap: xss,
            expires_at: xss,
            status: xss,
            spend: [],
          },
        ],
      },
      "/v1/daari/teams": {
        teams: [{ team_id: xss, name: xss, key_count: 1, rpm: 1, rpd: 1, spend: [] }],
      },
      "/v1/daari/report": {
        ...REPORT,
        teams: [{ team: xss, requests: 1, cache_hits: 0, estimated_saved_usd: 0 }],
        model_group_spend: [{ model_group: xss, window: xss, spend_usd: 0.1, budget_usd: 1 }],
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.equal(dom.window.__xss, undefined, "onerror / script must not run");
  assert.equal(doc.querySelectorAll("img").length, 0, "no injected img elements");
  assert.equal(doc.querySelectorAll("#tiers-table script").length, 0);
  assert.equal(doc.querySelectorAll("#soft-warnings-table script").length, 0);
  assert.equal(doc.querySelectorAll("#backends-table script").length, 0);
  assert.equal(doc.querySelectorAll("#traces-table script").length, 0);
  assert.equal(doc.querySelectorAll("#admin-keys-table script").length, 0);
  assert.equal(doc.querySelectorAll("#admin-teams-table script").length, 0);
  assert.equal(doc.querySelectorAll("#report-teams-table script").length, 0);
  assert.match(doc.getElementById("tiers-table").textContent, /onerror/);
  assert.match(doc.getElementById("backends-table").textContent, /onerror/);
  assert.match(doc.getElementById("traces-table").textContent, /onerror/);
  assert.match(doc.getElementById("admin-keys-table").textContent, /onerror/);
  assert.match(doc.getElementById("admin-teams-table").textContent, /onerror/);
});

test("admin keys and teams tables render from inventory endpoints", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const keyRows = [...doc.querySelectorAll("#admin-keys-table tr")];
  assert.equal(keyRows.length, 1);
  assert.match(keyRows[0].textContent, /alice/);
  assert.match(keyRows[0].textContent, /L3/);
  assert.match(keyRows[0].textContent, /0\.25/);
  assert.match(doc.getElementById("admin-keys-status").textContent, /1 key/);

  const teamRows = [...doc.querySelectorAll("#admin-teams-table tr")];
  assert.equal(teamRows.length, 1);
  assert.match(teamRows[0].textContent, /eng/);
  assert.match(teamRows[0].textContent, /60/);
  assert.match(doc.getElementById("admin-teams-status").textContent, /1 team/);
});

test("report spend breakdown renders teams and model_group_spend", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const teamRows = [...doc.querySelectorAll("#report-teams-table tr")];
  assert.equal(teamRows.length, 2);
  assert.match(teamRows.map((r) => r.textContent).join("|"), /eng/);
  assert.match(teamRows.map((r) => r.textContent).join("|"), /ops/);

  const groupRows = [...doc.querySelectorAll("#report-model-group-spend-table tr")];
  assert.equal(groupRows.length, 2);
  assert.match(groupRows.map((r) => r.textContent).join("|"), /chat/);
  assert.match(groupRows.map((r) => r.textContent).join("|"), /embed/);
});

test("index.html ships a restrictive CSP meta", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const meta = dom.window.document.querySelector('meta[http-equiv="Content-Security-Policy"]');
  assert.ok(meta, "CSP meta required");
  assert.match(meta.content, /default-src 'self'/);
  assert.match(meta.content, /script-src 'self'/);
});

test("config editor Load/Save include Authorization when API key set", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/config": {
        routing: { confidence_threshold: 0.7, prefer: "balanced" },
        frontier: { daily_budget_usd: 1.5 },
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const keyInput = doc.getElementById("api-key");
  keyInput.value = "vk-token";
  keyInput.dispatchEvent(new dom.window.Event("change", { bubbles: true }));

  doc.getElementById("cfg-load").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();

  const loadCall = [...fetch.calls].reverse().find((c) => c.url.includes("/v1/daari/config"));
  assert.equal(loadCall?.init?.headers?.Authorization, "Bearer vk-token");

  doc.getElementById("cfg-save").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();

  const saveCall = [...fetch.calls]
    .reverse()
    .find((c) => c.url.includes("/v1/daari/config") && c.init?.method === "PATCH");
  assert.equal(saveCall?.init?.headers?.Authorization, "Bearer vk-token");
});

test("401 on stats shows auth hint in status", async (t) => {
  const fetch = fakeFetch(routes({ "/v1/daari/stats": { status: 401 } }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const status = dom.window.document.getElementById("status").textContent;
  assert.match(status, /API key|Bearer|401/i);
});
