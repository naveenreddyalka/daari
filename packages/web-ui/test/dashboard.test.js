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
  errors_by_status: { "503": 2, "500": 1 },
  backends: [
    { id: "gpu-a", healthy: true, circuit: "closed", outstanding: 1 },
    { id: "gpu-b", healthy: false, circuit: "open", outstanding: 0 },
  ],
  backend_summary: { total: 2, healthy: 1, unhealthy: 1, open_circuit: 1 },
  systemone_breaker: [
    { base: "http://vllm.local:8000", state: "open", rejects: 2, cooldown_seconds: 30 },
  ],
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
      last_used_at: "2026-10-11T12:00:00+00:00",
      status: "active",
      priority: "high",
      cache_scope: "team",
      max_in_flight: 3,
      user_rpd: 200,
      user_daily_usd_cap: 2.5,
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
      priority: "normal",
      cache_scope: "key",
      max_in_flight: 5,
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
    "/v1/daari/anthropic/enforcement": { profiles: [], enforced_count: 0 },
    "/v1/org-learning/profile": { status: 404 },
    "/ready": { status: "ready", schema_ok: true },
    ...overrides,
  };
}

test("schema lag banner shows when /ready reports schema_ok false", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/ready": { __http: 503, status: "not_ready", schema_ok: false },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const banner = dom.window.document.getElementById("schema-ok-banner");
  assert.ok(banner);
  assert.equal(banner.hidden, false);
  assert.match(banner.textContent, /schema/i);
  assert.equal(banner.innerHTML.includes("<"), false);
});

test("schema lag banner stays hidden when schema_ok is true", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const banner = dom.window.document.getElementById("schema-ok-banner");
  assert.ok(banner);
  assert.equal(banner.hidden, true);
});

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

test("errors by status table renders from stats", async (t) => {
  const fetch = fakeFetch(routes());
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const rows = [...doc.querySelectorAll("#errors-by-status-table tr")];
  assert.equal(rows.length, 2);
  const text = rows.map((r) => r.textContent).join("|");
  assert.match(text, /500/);
  assert.match(text, /503/);
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
  const s1 = doc.getElementById("systemone-breaker-status");
  assert.match(s1.textContent, /vllm\.local:8000=open/);
  assert.match(s1.textContent, /rejects 2/);
  assert.ok(s1.classList.contains("metric-warn"), "open systemone breaker warns");
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
            last_used_at: xss,
            status: xss,
            priority: xss,
            cache_scope: xss,
            max_in_flight: 1,
            spend: [],
          },
        ],
      },
      "/v1/daari/teams": {
        teams: [
          {
            team_id: xss,
            name: xss,
            key_count: 1,
            rpm: 1,
            rpd: 1,
            priority: xss,
            cache_scope: xss,
            max_in_flight: 1,
            spend: [],
          },
        ],
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
  assert.match(keyRows[0].textContent, /2026-10-11T12:00:00/);
  assert.match(keyRows[0].textContent, /high/);
  assert.match(keyRows[0].textContent, /team/);
  const keyCells = [...keyRows[0].querySelectorAll("td")].map((td) => td.textContent);
  assert.ok(keyCells.includes("3"), `expected max_in_flight 3 in ${keyCells.join("|")}`);
  assert.ok(keyCells.includes("200"), `expected user_rpd 200 in ${keyCells.join("|")}`);
  assert.ok(keyCells.includes("2.5"), `expected user_daily_usd_cap 2.5 in ${keyCells.join("|")}`);
  assert.match(doc.getElementById("admin-keys-status").textContent, /1 key/);

  const teamRows = [...doc.querySelectorAll("#admin-teams-table tr")];
  assert.equal(teamRows.length, 1);
  assert.match(teamRows[0].textContent, /eng/);
  assert.match(teamRows[0].textContent, /60/);
  assert.match(teamRows[0].textContent, /normal/);
  assert.match(teamRows[0].textContent, /key/);
  const teamCells = [...teamRows[0].querySelectorAll("td")].map((td) => td.textContent);
  assert.ok(teamCells.includes("5"), `expected max_in_flight 5 in ${teamCells.join("|")}`);
  assert.match(doc.getElementById("admin-teams-status").textContent, /1 team/);
});

test("admin keys status and idle_days filters build query and render rows", async (t) => {
  const filteredKeys = {
    keys: [
      { ...ADMIN_KEYS.keys[0], name: "idle-alice" },
      { ...ADMIN_KEYS.keys[0], key_id: "def456", name: "idle-bob" },
      { ...ADMIN_KEYS.keys[0], key_id: "ghi789", name: "idle-carol" },
    ],
    has_more: true,
  };
  const base = fakeFetch(routes());
  const fetch = async (url, init) => {
    const u = String(url);
    if (u.includes("/v1/daari/keys?") && u.includes("status=active") && u.includes("idle_days=30")) {
      fetch.calls.push({ url: u, init });
      return { ok: true, status: 200, statusText: "OK", json: async () => filteredKeys };
    }
    return base(url, init);
  };
  fetch.calls = base.calls;

  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  doc.getElementById("admin-keys-status-filter").value = "active";
  doc.getElementById("admin-keys-idle-days").value = "30";
  doc.getElementById("admin-keys-status-filter").dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();

  const filteredCalls = fetch.calls.filter(
    (c) => c.url.includes("/v1/daari/keys?") && c.url.includes("status=active") && c.url.includes("idle_days=30")
  );
  assert.ok(filteredCalls.length >= 1, `expected filtered keys fetch, got ${JSON.stringify(fetch.calls)}`);
  const keyRows = [...doc.querySelectorAll("#admin-keys-table tr")];
  assert.equal(keyRows.length, 3);
  assert.match(doc.getElementById("admin-keys-status").textContent, /3 idle key/);
  assert.match(doc.getElementById("admin-keys-status").textContent, /More available/);

  doc.getElementById("admin-keys-status-filter").value = "";
  doc.getElementById("admin-keys-idle-days").value = "";
  doc.getElementById("admin-keys-idle-days").dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();
  const cleared = fetch.calls.filter((c) => /\/v1\/daari\/keys$/.test(c.url) || c.url.endsWith("/v1/daari/keys"));
  assert.ok(cleared.length >= 1, "clearing filters restores unfiltered URL");
  assert.equal([...doc.querySelectorAll("#admin-keys-table tr")].length, 1);
});

test("admin keys show never when last_used_at is null", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/keys": {
        keys: [
          {
            ...ADMIN_KEYS.keys[0],
            last_used_at: null,
            priority: "low",
            cache_scope: "global",
          },
        ],
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const cells = [...doc.querySelectorAll("#admin-keys-table tr td")].map((td) => td.textContent);
  assert.ok(cells.includes("never"), `expected never in ${cells.join("|")}`);
  assert.ok(cells.includes("low"));
  assert.ok(cells.includes("global"));
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

test("events panel fetches team filter and renders rows as text", async (t) => {
  const xss = '<img src=x onerror=window.__xss=1><script>window.__xss=1</script>';
  const fetch = fakeFetch(
    routes({
      "/v1/daari/events": {
        events: [
          {
            id: 9,
            ts: xss,
            event: "chat",
            payload: { team_id: "eng", note: xss },
          },
        ],
        total: 2,
        limit: 20,
        offset: 0,
        has_more: true,
        next_cursor: "9",
      },
      "/v1/daari/lockouts": {
        lockouts: [{ prefix: xss, expires_in_seconds: 12 }],
      },
      "/v1/daari/keys/unlock": { status: "ok", prefix: "abcdefghij", cleared: true },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const team = doc.getElementById("events-team-filter");
  team.value = "eng";
  team.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();

  const eventCalls = fetch.calls.filter((c) => c.url.includes("/v1/daari/events"));
  assert.ok(eventCalls.some((c) => c.url.includes("limit=20")));
  assert.ok(eventCalls.some((c) => c.url.includes("team_id=eng")));
  const eventsText = doc.getElementById("events-table").textContent;
  assert.match(eventsText, /chat/);
  assert.match(eventsText, /eng/);
  assert.match(eventsText, /onerror/);
  assert.match(eventsText, /"team_id":"eng"/);
  assert.equal(doc.querySelectorAll("#events-table script").length, 0);
  assert.equal(doc.querySelectorAll("#events-table img").length, 0);
  assert.equal(dom.window.__xss, undefined);

  const lockText = doc.getElementById("lockouts-table").textContent;
  assert.match(lockText, /onerror/);
  assert.match(lockText, /Unlock/);
  assert.equal(doc.querySelectorAll("#lockouts-table script").length, 0);

  doc.getElementById("events-next").dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();
  assert.ok(fetch.calls.some((c) => c.url.includes("/v1/daari/events") && c.url.includes("cursor=9")));

  const unlock = doc.querySelector("#lockouts-table button.lockout-unlock");
  unlock.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await settle();
  const unlockCall = fetch.calls.find(
    (c) => c.url.includes("/v1/daari/keys/unlock") && c.init?.method === "POST"
  );
  assert.ok(unlockCall);
  assert.match(unlockCall.init.body, /onerror/);
});

test("events panel key/kind filters hit the API and payload cell is text", async (t) => {
  const xss = '<img src=x onerror=window.__xss=1><script>window.__xss=1</script>';
  const fetch = fakeFetch(
    routes({
      "/v1/daari/events": {
        events: [
          {
            id: 3,
            ts: "2026-10-20T00:00:00+00:00",
            event: "budget_alert",
            payload: { key_id: "k1", team_id: "ops", detail: xss },
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
        next_cursor: "",
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const key = doc.getElementById("events-key-filter");
  const kind = doc.getElementById("events-kind-filter");
  assert.ok(key);
  assert.ok(kind);
  key.value = "k1";
  kind.value = "budget_alert";
  key.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();
  kind.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();

  const eventCalls = fetch.calls.filter((c) => c.url.includes("/v1/daari/events"));
  assert.ok(eventCalls.some((c) => c.url.includes("key_id=k1")));
  assert.ok(eventCalls.some((c) => c.url.includes("kind=budget_alert")));
  const eventsText = doc.getElementById("events-table").textContent;
  assert.match(eventsText, /budget_alert/);
  assert.match(eventsText, /"key_id":"k1"/);
  assert.match(eventsText, /onerror/);
  assert.equal(doc.querySelectorAll("#events-table script").length, 0);
  assert.equal(doc.querySelectorAll("#events-table img").length, 0);
  assert.equal(dom.window.__xss, undefined);
});

test("events panel since/until filters hit the API", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/events": {
        events: [
          {
            id: 4,
            ts: "2026-10-20T14:05:00+00:00",
            event: "chat",
            payload: { team_id: "eng" },
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
        next_cursor: "",
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const since = doc.getElementById("events-since-filter");
  const until = doc.getElementById("events-until-filter");
  assert.ok(since);
  assert.ok(until);
  since.value = "2026-10-20T14:00:00Z";
  until.value = "2026-10-20T14:10:00Z";
  since.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();
  until.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  await settle();

  const eventCalls = fetch.calls.filter((c) => c.url.includes("/v1/daari/events"));
  assert.ok(eventCalls.some((c) => c.url.includes("since=2026-10-20T14%3A00%3A00Z") || c.url.includes("since=2026-10-20T14:00:00Z")));
  assert.ok(eventCalls.some((c) => c.url.includes("until=2026-10-20T14%3A10%3A00Z") || c.url.includes("until=2026-10-20T14:10:00Z")));
});

test("spend export downloads csv via /v1/daari/spend/export", async (t) => {
  const csvBody = "timestamp,cost_usd\n2026-10-01T00:00:00Z,0.01\n";
  const fetch = fakeFetch(
    routes({
      "/v1/daari/spend/export": { __http: 200, __text: csvBody },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const downloads = [];
  dom.window.URL.createObjectURL = (blob) => {
    downloads.push(blob);
    return "blob:daari-spend-test";
  };
  dom.window.URL.revokeObjectURL = () => {};
  const clickSpy = [];
  const origCreate = dom.window.document.createElement.bind(dom.window.document);
  dom.window.document.createElement = (tag) => {
    const el = origCreate(tag);
    if (tag === "a") {
      el.click = () => {
        clickSpy.push({ href: el.href, download: el.download });
      };
    }
    return el;
  };

  const apiKey = doc.getElementById("api-key");
  if (apiKey) {
    apiKey.value = "analyst-key";
    apiKey.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  }
  doc.getElementById("spend-export-since").value = "7d";
  doc.getElementById("spend-export-format").value = "csv";
  doc.getElementById("spend-export-model").value = "%:cloud";
  doc.getElementById("spend-export-usage-speed").value = "fast";
  doc.getElementById("spend-export-download").click();
  await settle(20);

  const call = fetch.calls.find((c) => c.url.includes("/v1/daari/spend/export"));
  assert.ok(call, "expected spend/export fetch");
  assert.match(call.url, /since=7d/);
  assert.match(call.url, /format=csv/);
  assert.match(call.url, /model=%25%3Acloud|model=%25:cloud/);
  assert.match(call.url, /usage_speed=fast/);
  assert.equal(call.init?.headers?.Authorization, "Bearer analyst-key");
  assert.equal(downloads.length, 1);
  assert.equal(clickSpy.length, 1);
  assert.match(clickSpy[0].download, /\.csv$/);
  assert.match(doc.getElementById("spend-export-status").textContent, /download/i);
});

test("spend export shows analyst 403 message", async (t) => {
  const fetch = fakeFetch(routes({ "/v1/daari/spend/export": { status: 403 } }));
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  doc.getElementById("spend-export-download").click();
  await settle(20);

  const status = doc.getElementById("spend-export-status").textContent;
  assert.match(status, /403/);
  assert.match(status, /analyst/i);
  assert.ok(fetch.calls.some((c) => c.url.includes("/v1/daari/spend/export")));
});

test("spend export sends team and until query params", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/spend/export": { __http: 200, __text: "timestamp,cost_usd\n" },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  dom.window.URL.createObjectURL = () => "blob:test";
  dom.window.URL.revokeObjectURL = () => {};
  const origCreate = dom.window.document.createElement.bind(dom.window.document);
  dom.window.document.createElement = (tag) => {
    const el = origCreate(tag);
    if (tag === "a") {
      el.click = () => {};
    }
    return el;
  };

  doc.getElementById("spend-export-team").value = "platform";
  doc.getElementById("spend-export-until").value = "2026-10-23T00:00:00Z";
  doc.getElementById("spend-export-download").click();
  await settle(20);

  const call = fetch.calls.find((c) => c.url.includes("/v1/daari/spend/export"));
  assert.ok(call, "expected spend/export fetch");
  assert.match(call.url, /team=platform/);
  assert.match(
    call.url,
    /until=2026-10-23T00%3A00%3A00Z|until=2026-10-23T00:00:00Z/
  );
});

test("spend report loads rows via /v1/daari/spend/report with group_by and bucket", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/spend/report": {
        rows: [
          {
            bucket: "2026-06-01",
            model: "claude-haiku-4-5",
            service_tier: "default",
            requests: 2,
            cost_usd: 0.15,
            input_tokens: 150,
            output_tokens: 15,
            cost_avoided_usd: 0.01,
          },
        ],
        group_by: ["model", "service_tier"],
        bucket: "day",
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const apiKey = doc.getElementById("api-key");
  if (apiKey) {
    apiKey.value = "analyst-key";
    apiKey.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  }

  for (const dim of ["model", "service_tier"]) {
    const box = doc.querySelector(`input[name="spend-report-group-by"][value="${dim}"]`);
    assert.ok(box, `expected group_by checkbox for ${dim}`);
    box.checked = true;
  }
  doc.getElementById("spend-report-since").value = "7d";
  doc.getElementById("spend-report-bucket").value = "day";
  doc.getElementById("spend-report-load").click();
  await settle(20);

  const call = fetch.calls.find((c) => c.url.includes("/v1/daari/spend/report"));
  assert.ok(call, "expected spend/report fetch");
  assert.match(call.url, /since=7d/);
  assert.match(call.url, /group_by=model%2Cservice_tier|group_by=model,service_tier/);
  assert.match(call.url, /bucket=day/);
  assert.equal(call.init?.headers?.Authorization, "Bearer analyst-key");

  const rows = [...doc.querySelectorAll("#spend-report-table tr")];
  assert.equal(rows.length, 1);
  const text = rows[0].textContent;
  assert.match(text, /claude-haiku-4-5/);
  assert.match(text, /default/);
  assert.match(text, /0\.15|0\.1500/);
  assert.match(doc.getElementById("spend-report-status").textContent, /1 row/i);
});

test("spend report surfaces API 400 detail in status", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/spend/report": {
        __http: 400,
        detail: "bucket must be day or month",
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const modelBox = doc.querySelector('input[name="spend-report-group-by"][value="model"]');
  assert.ok(modelBox);
  modelBox.checked = true;
  doc.getElementById("spend-report-bucket").value = "day";
  doc.getElementById("spend-report-load").click();
  await settle(20);

  const status = doc.getElementById("spend-report-status").textContent;
  assert.match(status, /400/);
  assert.match(status, /bucket must be day or month/);
  assert.ok(fetch.calls.some((c) => c.url.includes("/v1/daari/spend/report")));
  // Do not leave a silent empty success table — status carries the error.
  assert.match(status, /failed|error|400/i);
});

test("systemone breaker reset posts and refreshes status", async (t) => {
  let statsPayload = {
    ...STATS,
    systemone_breaker: [
      { base: "http://vllm.local:8000", state: "open", rejects: 2, cooldown_seconds: 30 },
    ],
  };
  const closedBreaker = [
    { base: "http://vllm.local:8000", state: "closed", rejects: 2, cooldown_seconds: 30 },
  ];
  const baseFetch = fakeFetch(routes());
  const calls = [];
  const wrapped = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    wrapped.calls = calls;
    if (String(url).includes("/v1/daari/systemone/breaker/reset")) {
      statsPayload = { ...STATS, systemone_breaker: closedBreaker };
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({ status: "ok", systemone_breaker: closedBreaker }),
        text: async () => "",
      };
    }
    if (String(url).includes("/v1/daari/stats")) {
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => statsPayload,
        text: async () => JSON.stringify(statsPayload),
      };
    }
    return baseFetch(url, init);
  };
  wrapped.calls = calls;

  const dom = loadDashboard({ fetch: wrapped });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const status = doc.getElementById("systemone-breaker-status");
  assert.match(status.textContent, /open/);
  const apiKey = doc.getElementById("api-key");
  if (apiKey) {
    apiKey.value = "admin-key";
    apiKey.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  }
  doc.getElementById("systemone-breaker-reset").click();
  await settle(30);

  const resetCall = calls.find((c) => c.url.includes("/v1/daari/systemone/breaker/reset"));
  assert.ok(resetCall, "expected breaker reset POST");
  assert.equal(resetCall.init?.method, "POST");
  assert.equal(resetCall.init?.headers?.Authorization, "Bearer admin-key");
  assert.match(status.textContent, /closed/);
  assert.match(doc.getElementById("systemone-breaker-reset-status").textContent, /reset/i);
});

test("systemone breaker reset shows admin 403 message", async (t) => {
  const fetch = fakeFetch(
    routes({ "/v1/daari/systemone/breaker/reset": { status: 403 } })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  doc.getElementById("systemone-breaker-reset").click();
  await settle(20);

  const msg = doc.getElementById("systemone-breaker-reset-status").textContent;
  assert.match(msg, /403/);
  assert.match(msg, /admin/i);
  assert.ok(
    fetch.calls.some((c) => c.url.includes("/v1/daari/systemone/breaker/reset"))
  );
});

test("enforcement panel renders profiles as text (XSS-safe)", async (t) => {
  const xss = '<img src=x onerror=window.__xss=1><script>window.__xss=1</script>';
  const fetch = fakeFetch(
    routes({
      "/v1/daari/anthropic/enforcement": {
        profiles: [
          {
            profile_id: xss,
            enforcement_status: "restricted",
            enforcement_actions: [{ type: xss }],
          },
        ],
        enforced_count: 1,
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  const table = doc.getElementById("enforcement-table");
  assert.match(table.textContent, /onerror/);
  assert.match(table.textContent, /restricted/);
  assert.equal(doc.querySelectorAll("#enforcement-table script").length, 0);
  assert.equal(doc.querySelectorAll("#enforcement-table img").length, 0);
  assert.equal(dom.window.__xss, undefined);
  assert.match(doc.getElementById("enforcement-status").textContent, /1 profile/);
  assert.ok(fetch.calls.some((c) => c.url.includes("/v1/daari/anthropic/enforcement")));
});

test("enforcement panel shows clear error when fetch fails", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/anthropic/enforcement": { status: 503 },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  assert.match(doc.getElementById("enforcement-status").textContent, /unavailable/i);
  assert.match(doc.getElementById("enforcement-table").textContent, /No synced/i);
});

test("cache invalidate form posts scope and shows removed counts", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/cache/invalidate": {
        removed: 3,
        l0_removed: 2,
        l1_removed: 1,
      },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  doc.getElementById("cache-invalidate-model").value = "llama";
  doc.getElementById("cache-invalidate-team").value = "eng";
  doc.getElementById("cache-invalidate-key").value = "k1";
  doc.getElementById("cache-invalidate-submit").click();
  await settle(20);

  const call = fetch.calls.find(
    (c) => c.url.includes("/v1/daari/cache/invalidate") && c.init?.method === "POST"
  );
  assert.ok(call, "expected cache invalidate POST");
  const body = JSON.parse(call.init.body);
  assert.equal(body.model, "llama");
  assert.equal(body.team_id, "eng");
  assert.equal(body.key_id, "k1");
  assert.match(doc.getElementById("cache-invalidate-status").textContent, /Removed 3/);
  assert.match(doc.getElementById("cache-invalidate-status").textContent, /L0 2/);
});

test("cache invalidate form shows error text on failure", async (t) => {
  const fetch = fakeFetch(
    routes({
      "/v1/daari/cache/invalidate": { status: 403 },
    })
  );
  const dom = loadDashboard({ fetch });
  t.after(() => dom.window.close());
  await settle();

  const doc = dom.window.document;
  doc.getElementById("cache-invalidate-submit").click();
  await settle(20);

  assert.match(doc.getElementById("cache-invalidate-status").textContent, /Invalidate failed/);
  assert.match(doc.getElementById("cache-invalidate-status").textContent, /403/);
});
