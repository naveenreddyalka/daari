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
