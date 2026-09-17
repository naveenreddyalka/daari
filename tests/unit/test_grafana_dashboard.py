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
