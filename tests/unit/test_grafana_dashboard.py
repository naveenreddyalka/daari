"""Smoke: Grafana dashboard JSON loads and exposes TTFT / soft-warn panels."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "deploy" / "grafana" / "daari-dashboard.json"


def test_grafana_dashboard_includes_ttft_panel():
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert payload["title"] == "daari"
    assert payload["uid"] == "daari-overview"
    panels = payload["panels"]
    assert isinstance(panels, list) and panels

    ttft = next((p for p in panels if "TTFT" in p.get("title", "")), None)
    assert ttft is not None, "expected a TTFT panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in ttft.get("targets", [])]
    assert any("daari_ttft_ms_bucket" in expr for expr in exprs)
    assert any("histogram_quantile(0.50" in expr for expr in exprs)
    assert any("histogram_quantile(0.95" in expr for expr in exprs)


def test_grafana_dashboard_includes_soft_warnings_panel():
    """Soft-band counters from #526 should be visible on the overview (#537)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    soft = next(
        (p for p in payload["panels"] if "Soft warning" in p.get("title", "")),
        None,
    )
    assert soft is not None, "expected a soft-warnings panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in soft.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_rejects_panel():
    """Hard 402/429 counters from #551 should be visible on the overview."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    rejects = next(
        (p for p in payload["panels"] if "Hard reject" in p.get("title", "")),
        None,
    )
    assert rejects is not None, "expected a hard-rejects panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in rejects.get("targets", [])]
    assert any("daari_rejects_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_rate_limit_degraded_panel():
    """Redis degrade gauge from #553 should be visible on the overview."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Rate-limit Redis degraded" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a rate-limit degraded panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_rate_limit_degraded" in expr for expr in exprs)


def test_grafana_dashboard_includes_ttft_preference_panel():
    """TTFT-aware routing counter from #539 should be visible (#571)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "TTFT preference" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a TTFT preference panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_ttft_preference_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_backend_pool_panel():
    """Local pool health/outstanding gauges should be on the overview (#583)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Backend pool" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a backend pool panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_backend_up" in expr for expr in exprs)
    assert any("daari_backend_outstanding" in expr for expr in exprs)


def test_grafana_dashboard_includes_concurrency_gate_panel():
    """In-flight vs max (and queued) concurrency gauges from the rate limiter (#583)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Concurrency gate" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a concurrency gate panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_rate_limit_in_flight" in expr for expr in exprs)
    assert any("daari_rate_limit_in_flight_max" in expr for expr in exprs)
    assert any("daari_rate_limit_queued" in expr for expr in exprs)


def test_grafana_dashboard_includes_scoped_in_flight_panel():
    """Per-key/team/model in-flight gauges next to the global concurrency gate (#1638)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Scoped in-flight" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a scoped in-flight panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    legends = [t.get("legendFormat", "") for t in panel.get("targets", [])]
    assert any("daari_in_flight" in expr and "daari_in_flight_max" not in expr for expr in exprs)
    assert any("daari_in_flight_max" in expr for expr in exprs)
    assert any("{{scope}}" in leg and "{{id}}" in leg for leg in legends)


def test_grafana_dashboard_includes_upstream_retries_panel():
    """Upstream retry counter should be visible on the overview (#601)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Upstream retries" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected an upstream-retries panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_upstream_retries_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_cache_false_hits_avoided_panel():
    """L1 verification veto counter should be visible on the overview (#601)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "False-hits avoided" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a false-hits-avoided panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_cache_false_hits_avoided_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_budget_alerts_panel():
    """Budget threshold-crossing counter should be visible on the overview (#601)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Budget alert" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a budget-alerts panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_budget_alerts_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_mcp_tool_ingress_panel():
    """MCP tool-call outcomes should be visible on the overview (#619)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "MCP tool" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected an MCP tool ingress panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_mcp_tool_calls_total" in expr for expr in exprs)
    assert any("outcome" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_team_budget_remaining_panel():
    """Team USD remaining gauges from #616 should be visible (#627)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Team budget remaining" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a team budget remaining panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_team_budget_remaining_usd" in expr for expr in exprs)
    assert any("daari_team_budget_limit_usd" in expr for expr in exprs)


def test_grafana_dashboard_includes_team_rate_limit_remaining_panel():
    """Team RPM/TPM remaining gauges from #617 should be visible (#627)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "Team rate-limit remaining" in p.get("title", "")
        ),
        None,
    )
    assert panel is not None, (
        "expected a team rate-limit remaining panel in daari-dashboard.json"
    )
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_team_rate_limit_remaining" in expr for expr in exprs)
    assert any("daari_team_rate_limit_limit" in expr for expr in exprs)


def test_grafana_dashboard_includes_key_rate_limit_remaining_panel():
    """Per-key RPD remaining gauges should be visible on the overview (#750)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "Key rate-limit remaining" in p.get("title", "")
        ),
        None,
    )
    assert panel is not None, (
        "expected a key rate-limit remaining panel in daari-dashboard.json"
    )
    targets = panel.get("targets", [])
    exprs = [t.get("expr", "") for t in targets]
    legends = [t.get("legendFormat", "") for t in targets]
    assert any("daari_key_rate_limit_remaining" in expr for expr in exprs)
    assert any("daari_key_rate_limit_limit" in expr for expr in exprs)
    assert any("{{key}}" in legend and "{{kind}}" in legend for legend in legends)


def test_grafana_dashboard_includes_soft_usd_budget_warnings_panel():
    """Dedicated soft USD budget warn series from #626 should be visible (#636)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Soft USD budget" in p.get("title", "")),
        None,
    )
    assert panel is not None, (
        "expected a Soft USD budget warnings panel in daari-dashboard.json"
    )
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any('kind="budget"' in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)

def test_grafana_dashboard_includes_tier_shadow_panel():
    """Tier shadow agree/disagree counter should be visible on the overview (#689)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Tier shadow" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a tier-shadow panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_tier_shadow_samples_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)

def test_grafana_dashboard_includes_boundary_decisions_panel():
    """Product-boundary decision counter should be visible on the overview (#690)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Boundary decisions" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a boundary-decisions panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_boundary_decisions_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_cancelled_requests_panel():
    """Cancelled-request phases should be visible on the overview (#788)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Cancelled requests" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected a cancelled-requests panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_cancelled_requests_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_deadline_exceeded_panel():
    """Request-deadline burns should be visible on the overview (#788, #837)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "deadline exceeded" in p.get("title", "").lower()),
        None,
    )
    assert panel is not None, "expected a deadline-exceeded panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_request_deadline_exceeded_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)
    description = panel.get("description", "").lower()
    assert "chat-only" not in description or "not chat-only" in description
    assert "audio" in description
    assert "embed" in description
    assert "mcp" in description


def test_grafana_dashboard_includes_compact_to_fit_applied_panel():
    """Compact-to-fit trim counter should be visible on the overview (#1391)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if p.get("title") == "Compact-to-fit applied"
        ),
        None,
    )
    assert panel is not None, "expected a compact-to-fit panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_compact_to_fit_applied_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_compact_to_fit_tokens_dropped_panel():
    """Estimated tokens dropped by compact-to-fit should chart on overview (#1400)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "tokens dropped" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a tokens-dropped panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_compact_to_fit_tokens_dropped_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_decision_classifier_panels():
    """Classifier outcome rate and latency should chart on the overview (#1483)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    outcome = next(
        (
            p
            for p in payload["panels"]
            if "decision classifier" in p.get("title", "").lower()
            and "latency" not in p.get("title", "").lower()
        ),
        None,
    )
    assert outcome is not None, "expected a decision-classifier outcome panel"
    outcome_exprs = [t.get("expr", "") for t in outcome.get("targets", [])]
    assert any("daari_decision_classifier_total" in expr for expr in outcome_exprs)
    assert any("outcome" in expr for expr in outcome_exprs)
    assert any("rate(" in expr for expr in outcome_exprs)

    latency = next(
        (
            p
            for p in payload["panels"]
            if "decision classifier" in p.get("title", "").lower()
            and "latency" in p.get("title", "").lower()
        ),
        None,
    )
    assert latency is not None, "expected a decision-classifier latency panel"
    latency_exprs = [t.get("expr", "") for t in latency.get("targets", [])]
    assert any("daari_decision_classifier_latency_ms" in expr for expr in latency_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in latency_exprs)
    assert any("histogram_quantile(0.95" in expr for expr in latency_exprs)


def test_grafana_dashboard_includes_mcp_grant_denied_panel():
    """MCP grant fail-closed denials should chart on the overview (#1401)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "grant denied" in p.get("title", "").lower()
            or p.get("title") == "MCP grant denied"
        ),
        None,
    )
    assert panel is not None, "expected an MCP grant-denied panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_mcp_grant_denied_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_virtual_keys_lifecycle_panel():
    """Virtual-key lifecycle gauges from #1546 should chart on overview (#1564)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "virtual key" in p.get("title", "").lower()
            or "virtual_keys" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a virtual-keys lifecycle panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_virtual_keys" in expr for expr in exprs)
    assert any('status="expired"' in expr for expr in exprs)
    assert any('status="expiring_soon"' in expr for expr in exprs)


def test_grafana_dashboard_includes_retired_rejects_series():
    """Retired-model hard rejects from #1549 should chart on overview (#1564)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panels = payload["panels"]
    dedicated = next(
        (
            p
            for p in panels
            if "retired" in p.get("title", "").lower()
        ),
        None,
    )
    exprs: list[str] = []
    if dedicated is not None:
        exprs = [t.get("expr", "") for t in dedicated.get("targets", [])]
    else:
        hard = next(
            (p for p in panels if "Hard reject" in p.get("title", "")),
            None,
        )
        assert hard is not None, "expected hard-rejects or retired-rejects panel"
        exprs = [t.get("expr", "") for t in hard.get("targets", [])]
    assert any("daari_rejects_total" in expr for expr in exprs)
    assert any('kind="retired"' in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_cache_invalidate_panels():
    """Admin cache-invalidate series should be visible on the overview (#1660)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    by_scope = next(
        (p for p in payload["panels"] if "Cache invalidate by scope" in p.get("title", "")),
        None,
    )
    assert by_scope is not None, "expected a cache-invalidate scope/result panel"
    exprs = [t.get("expr", "") for t in by_scope.get("targets", [])]
    assert any("daari_cache_invalidate_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)

    removed = next(
        (
            p
            for p in payload["panels"]
            if "Cache invalidate entries removed" in p.get("title", "")
        ),
        None,
    )
    assert removed is not None, "expected a cache-invalidate entries-removed panel"
    removed_exprs = [t.get("expr", "") for t in removed.get("targets", [])]
    assert any("daari_cache_invalidate_entries_removed_total" in expr for expr in removed_exprs)
    assert any("rate(" in expr for expr in removed_exprs)


def test_grafana_dashboard_includes_errors_by_status_panel():
    """Errors series should break out HTTP status (#1685)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (p for p in payload["panels"] if "Errors by HTTP status" in p.get("title", "")),
        None,
    )
    assert panel is not None, "expected an errors-by-status panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("sum by (status)" in expr and "daari_errors_total" in expr for expr in exprs)
    assert any("status" in expr for expr in exprs)


def test_grafana_dashboard_panel_ids_are_unique() -> None:
    """Duplicate panel ids break Grafana import silently (#1574)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    ids = [p.get("id") for p in payload["panels"]]
    assert ids, "expected at least one panel"
    assert None not in ids, "every panel must have an id"
    assert len(ids) == len(set(ids)), f"duplicate panel ids: {ids}"


def test_grafana_dashboard_includes_cloud_vs_local_spend_share_panel():
    """Cloud vs local spend share should chart on the overview (#1802)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "cloud" in p.get("title", "").lower()
            and "local" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a cloud-vs-local spend share panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_frontier_spend_usd" in expr for expr in exprs)
    assert any("daari_requests_total" in expr for expr in exprs)


def test_grafana_dashboard_includes_fast_mode_request_rate_panel():
    """Fast-mode traffic should chart on the overview (#1802)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "fast" in p.get("title", "").lower()
            and "mode" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a fast-mode request-rate panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any("fast_degraded_to_standard" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_schema_ok_panel():
    """Local SQLite schema lag gauge should chart on the overview (#1823)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "schema" in p.get("title", "").lower()
            and "ok" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a schema_ok panel in daari-dashboard.json"
    assert panel.get("type") == "stat"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_schema_ok" in expr for expr in exprs)


def test_grafana_dashboard_includes_systemone_breaker_panel():
    """Systemone breaker events should chart on the overview (#1823)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "systemone" in p.get("title", "").lower()
            and "breaker" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a systemone breaker panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_systemone_breaker_total" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)
    assert any("event" in expr for expr in exprs)


def test_grafana_dashboard_includes_fleet_breaker_state_panel():
    """Fleet breaker state gauge should chart all families (#1932)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "breaker state" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a breaker-state panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_breaker_state" in expr for expr in exprs)



def test_grafana_dashboard_includes_gzip_panels():
    """Gzip outcome rate and byte counters should chart on the overview (#1872)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    outcomes = next(
        (
            p
            for p in payload["panels"]
            if "gzip" in p.get("title", "").lower()
            and "byte" not in p.get("title", "").lower()
        ),
        None,
    )
    assert outcomes is not None, "expected a gzip outcomes panel in daari-dashboard.json"
    outcome_exprs = [t.get("expr", "") for t in outcomes.get("targets", [])]
    assert any("daari_gzip_total" in expr for expr in outcome_exprs)
    assert any("rate(" in expr for expr in outcome_exprs)
    assert any("result" in expr for expr in outcome_exprs)

    bytes_panel = next(
        (
            p
            for p in payload["panels"]
            if "gzip" in p.get("title", "").lower()
            and "byte" in p.get("title", "").lower()
        ),
        None,
    )
    assert bytes_panel is not None, "expected a gzip bytes panel in daari-dashboard.json"
    byte_exprs = [t.get("expr", "") for t in bytes_panel.get("targets", [])]
    assert any("daari_gzip_uncompressed_bytes_total" in expr for expr in byte_exprs)
    assert any("daari_gzip_compressed_bytes_total" in expr for expr in byte_exprs)


def test_grafana_dashboard_includes_service_tier_degraded_panel():
    """OpenAI service_tier degrade soft-warnings should chart (#1889)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "service-tier" in p.get("title", "").lower()
            or "service_tier" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a service_tier_degraded panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any("service_tier_degraded" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_anthropic_sampling_stripped_panel():
    """Anthropic sampling-strip soft-warnings should chart (#1889)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "sampling" in p.get("title", "").lower()
            and "stripped" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected an anthropic_sampling_stripped panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any("anthropic_sampling_stripped" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_anthropic_document_stripped_panel():
    """Anthropic document-strip soft-warnings should chart (#1917)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "document" in p.get("title", "").lower()
            and "stripped" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected an anthropic_document_stripped panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any("anthropic_document_stripped" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_anthropic_citations_stripped_panel():
    """Anthropic citations-strip soft-warnings should chart (#1917)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "citation" in p.get("title", "").lower()
            and "stripped" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected an anthropic_citations_stripped panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_soft_warnings_total" in expr for expr in exprs)
    assert any("anthropic_citations_stripped" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_anthropic_enforced_profiles_panel():
    """Anthropic enforced-profiles gauge should chart (#1889)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "enforced" in p.get("title", "").lower()
            and "profile" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a daari_anthropic_enforced_profiles panel"
    assert panel.get("type") == "stat"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_anthropic_enforced_profiles" in expr for expr in exprs)


def test_grafana_dashboard_includes_cache_write_ttl_panel():
    """Cache-write tokens by TTL class should chart on the overview (#1872)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "cache write" in p.get("title", "").lower()
            or "cache-write" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a cache-write TTL panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_cache_write_tokens_total" in expr for expr in exprs)
    assert any("ttl" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_responses_webhooks_panel():
    """Completion webhook delivery counter should chart by result (#1935)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "responses" in p.get("title", "").lower()
            and "webhook" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected a responses webhooks panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_responses_webhooks_total" in expr for expr in exprs)
    assert any("by (result)" in expr or "by(result)" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)


def test_grafana_dashboard_includes_org_enforcement_webhooks_panel():
    """Org-enforcement webhook ingest counter should chart by result (#1935)."""
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = next(
        (
            p
            for p in payload["panels"]
            if "org" in p.get("title", "").lower()
            and "enforcement" in p.get("title", "").lower()
            and "webhook" in p.get("title", "").lower()
        ),
        None,
    )
    assert panel is not None, "expected an org enforcement webhooks panel"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("daari_org_enforcement_webhooks_total" in expr for expr in exprs)
    assert any("by (result)" in expr or "by(result)" in expr for expr in exprs)
    assert any("rate(" in expr for expr in exprs)
