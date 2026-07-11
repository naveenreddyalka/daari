import assert from "node:assert/strict";
import { test } from "node:test";

import { fakeFetch, loadDashboard, settle } from "./harness.js";

const STATS = {
  total_requests: 42,
  errors: 1,
  tiers: { L0: { count: 10, p50_ms: 1, p95_ms: 2 }, L3: { count: 32, p50_ms: 900, p95_ms: 2100 } },
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
    "/v1/daari/traces/abcd1234efgh": TRACE_DETAIL,
    "/v1/daari/traces": TRACES,
    "/v1/org-learning/profile": { status: 404 },
    ...overrides,
  };
}

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
    fetch.calls.some((url) => url.includes("/v1/daari/report?days=30")),
    "changing the window must refetch with days=30"
  );
});
