"""Prometheus + OTel modality parity for /mcp/proxy and MCP tasks (#1632)."""

from __future__ import annotations

import uuid

from daari.gateway.mcp_proxy import _record_proxy_call
from daari.gateway.mcp_tasks import McpTaskStore
from daari.observability.metrics import Metrics, genai_operation_name, infer_modality
from daari.observability.prometheus import render_prometheus


def test_mcp_modality_registered():
    assert infer_modality("mcp") == "mcp"
    assert infer_modality("L3", modality="mcp") == "mcp"
    assert genai_operation_name("mcp") == "mcp"
    assert genai_operation_name("mcp") != "chat"


def test_proxy_span_operation_name_is_mcp_not_chat():
    # Same call site as mcp_proxy.handle_proxy span attrs.
    assert genai_operation_name("mcp") == "mcp"


def test_record_proxy_call_increments_prom_series():
    metrics = Metrics()

    class Ctx:
        def __init__(self) -> None:
            self.metrics = metrics

    _record_proxy_call(Ctx(), tool="getPet", outcome="ok")
    _record_proxy_call(Ctx(), tool="getPet", outcome="deny")
    _record_proxy_call(Ctx(), tool="getPet", outcome="error")
    text = render_prometheus(metrics)
    assert 'daari_mcp_tool_calls_total{tool="proxy.getPet",outcome="ok"} 1' in text
    assert 'daari_mcp_tool_calls_total{tool="proxy.getPet",outcome="deny"} 1' in text
    assert 'daari_mcp_tool_calls_total{tool="proxy.getPet",outcome="error"} 1' in text
    assert 'daari_requests_total{tier="mcp",modality="mcp"} 1' in text


def test_mcp_task_lifecycle_counters_and_prometheus():
    metrics = Metrics()
    store = McpTaskStore(metrics=metrics)
    task = store.create(tool="route")
    store.complete(task.task_id, {"ok": True})
    other = store.create(tool="stats")
    store.fail(other.task_id, "boom")
    cancelled = store.create(tool="route")
    store.request_cancel(cancelled.task_id)
    store._record("polled", tool="route", task_id=task.task_id)
    text = render_prometheus(metrics)
    assert "# TYPE daari_mcp_tasks_total counter" in text
    assert 'daari_mcp_tasks_total{outcome="created"} 3' in text
    assert 'daari_mcp_tasks_total{outcome="completed"} 1' in text
    assert 'daari_mcp_tasks_total{outcome="failed"} 1' in text
    assert 'daari_mcp_tasks_total{outcome="cancelled"} 1' in text
    assert 'daari_mcp_tasks_total{outcome="polled"} 1' in text


def test_grafana_mcp_panel_includes_proxy_and_tasks():
    import json
    from pathlib import Path

    raw = Path("deploy/grafana/daari-dashboard.json").read_text(encoding="utf-8")
    dash = json.loads(raw)
    panel = next(p for p in dash["panels"] if p["title"] == "MCP tool ingress by outcome")
    exprs = [t["expr"] for t in panel["targets"]]
    assert any("daari_mcp_tool_calls_total" in e for e in exprs)
    assert any("proxy" in e for e in exprs)
    assert any("daari_mcp_tasks_total" in e for e in exprs)
    assert "proxy" in (panel.get("description") or "").lower()


def test_two_task_stores_with_shared_metrics_bucket():
    """Sanity: distinct memory stores can share one Metrics instance."""
    metrics = Metrics()
    a = McpTaskStore(path=None, metrics=metrics)
    b = McpTaskStore(path=None, metrics=metrics)
    a.create(tool=f"t-{uuid.uuid4().hex[:6]}")
    b.create(tool=f"t-{uuid.uuid4().hex[:6]}")
    snap = metrics.snapshot(include_histograms=True)
    assert snap["mcp_tasks"].get("created") == 2
