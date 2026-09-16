"""Smoke: Grafana dashboard JSON loads and exposes TTFT (#516)."""

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
