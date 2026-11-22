"""Grafana panels for input/output cost USD counters (#2273)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "deploy" / "grafana" / "daari-dashboard.json"
HELM_DASHBOARD = ROOT / "deploy" / "helm" / "daari" / "files" / "grafana" / "daari-dashboard.json"
METRICS_DOC = ROOT / "docs" / "developer" / "guides" / "observability" / "metrics-prometheus.md"


def _panels() -> list[dict]:
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))["panels"]


def test_grafana_has_input_and_output_cost_panels():
    panels = _panels()
    titles = {p.get("title", "") for p in panels}
    assert any("input" in t.lower() and "cost" in t.lower() for t in titles)
    assert any("output" in t.lower() and "cost" in t.lower() for t in titles) or any(
        "input" in t.lower() and "output" in t.lower() and "cost" in t.lower() for t in titles
    )
    cost_panels = [
        p
        for p in panels
        if "cost" in p.get("title", "").lower()
        and ("input" in p.get("title", "").lower() or "output" in p.get("title", "").lower())
    ]
    assert cost_panels
    exprs = " ".join(t.get("expr", "") for p in cost_panels for t in p.get("targets", []))
    assert "daari_cost_input_usd_total" in exprs
    assert "daari_cost_output_usd_total" in exprs
    descriptions = " ".join(p.get("description") or "" for p in cost_panels).lower()
    assert "sum" in descriptions
    assert "0/0" in descriptions or "0 / 0" in descriptions or "zero" in descriptions


def test_helm_grafana_dashboard_matches_source():
    assert DASHBOARD.read_bytes() == HELM_DASHBOARD.read_bytes()


def test_metrics_doc_cross_links_cost_split_panels():
    text = METRICS_DOC.read_text(encoding="utf-8")
    assert "daari_cost_input_usd_total" in text
    # Cross-link the Overview Grafana panel title for the Kong-style split.
    assert "Input / output cost USD" in text
