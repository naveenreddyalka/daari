"""Markdown export for usage reports and traces (issue #35)."""

from __future__ import annotations

import httpx
from typer.testing import CliRunner

from daari.cli.app import app
from daari.observability.render import report_markdown, trace_markdown

REPORT_PAYLOAD = {
    "enabled": True,
    "days": [
        {
            "day": "2026-07-10",
            "requests": 12,
            "cache_hits": 5,
            "prompt_chars": 2400,
            "completion_chars": 900,
            "tiers": {
                "L0": {"requests": 5, "cache_hits": 5, "prompt_chars": 500, "completion_chars": 200},
                "L3": {"requests": 6, "cache_hits": 0, "prompt_chars": 1500, "completion_chars": 600},
                "L6": {"requests": 1, "cache_hits": 0, "prompt_chars": 400, "completion_chars": 100},
            },
        }
    ],
    "totals": {
        "requests": 12,
        "cache_hits": 5,
        "local_requests": 11,
        "frontier_requests": 1,
        "estimated_saved_usd": 0.0123,
    },
}

TRACE_PAYLOAD = {
    "trace_id": "abc123def456",
    "tier": "L3",
    "category": "doc_qa",
    "ts": "2026-07-10T22:00:00+00:00",
    "steps": [
        {"step": "profile", "elapsed_ms": 0, "detail": {"category": "doc_qa", "complexity": "trivial"}},
        {"step": "l0_lookup", "elapsed_ms": 1, "detail": {"hit": False}},
        {"step": "tier_attempt", "elapsed_ms": 2, "detail": {"tier": "L3"}},
        {"step": "served", "elapsed_ms": 650, "detail": {"tier": "L3", "cache_hit": False}},
    ],
}


class TestReportMarkdown:
    def test_contains_day_table_and_summary(self):
        md = report_markdown(REPORT_PAYLOAD, days=7)
        assert md.startswith("# daari usage report")
        assert "| day | requests | cache hits |" in md
        assert "| 2026-07-10 | 12 | 5 |" in md
        assert "**Estimated saved:** $0.0123" in md
        assert "Frontier requests: 1" in md

    def test_tier_breakdown_rows(self):
        md = report_markdown(REPORT_PAYLOAD, days=7)
        assert "| L0 |" in md
        assert "| L6 |" in md

    def test_disabled_ledger(self):
        md = report_markdown({"enabled": False, "days": [], "totals": {}}, days=7)
        assert "ledger is disabled" in md


class TestTraceMarkdown:
    def test_header_and_timeline(self):
        md = trace_markdown(TRACE_PAYLOAD)
        assert md.startswith("# daari request trace `abc123def456`")
        assert "**Tier:** L3" in md
        assert "**Category:** doc_qa" in md
        assert "| +0ms | profile |" in md
        assert "| +650ms | served |" in md
        assert "tier=L3" in md


class TestCliExport:
    def _mock_httpx(self, monkeypatch, payload):
        def fake_get(url, timeout=5.0):
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=payload, request=request)

        monkeypatch.setattr(httpx, "get", fake_get)

    def test_report_format_markdown(self, monkeypatch):
        self._mock_httpx(monkeypatch, REPORT_PAYLOAD)
        result = CliRunner().invoke(app, ["report", "--format", "markdown"])
        assert result.exit_code == 0
        assert "# daari usage report" in result.stdout

    def test_report_out_writes_file(self, monkeypatch, tmp_path):
        self._mock_httpx(monkeypatch, REPORT_PAYLOAD)
        out = tmp_path / "report.md"
        result = CliRunner().invoke(app, ["report", "--format", "markdown", "--out", str(out)])
        assert result.exit_code == 0
        assert out.read_text(encoding="utf-8").startswith("# daari usage report")
        assert str(out) in result.stdout

    def test_trace_format_markdown(self, monkeypatch):
        self._mock_httpx(monkeypatch, TRACE_PAYLOAD)
        result = CliRunner().invoke(app, ["trace", "abc123def456", "--format", "markdown"])
        assert result.exit_code == 0
        assert "# daari request trace `abc123def456`" in result.stdout

    def test_trace_out_writes_file(self, monkeypatch, tmp_path):
        self._mock_httpx(monkeypatch, TRACE_PAYLOAD)
        out = tmp_path / "trace.md"
        result = CliRunner().invoke(app, ["trace", "abc123def456", "--out", str(out)])
        assert result.exit_code == 0
        assert "# daari request trace" in out.read_text(encoding="utf-8")

    def test_report_default_text_unchanged(self, monkeypatch):
        self._mock_httpx(monkeypatch, REPORT_PAYLOAD)
        result = CliRunner().invoke(app, ["report"])
        assert result.exit_code == 0
        assert "total requests:    12" in result.stdout
        assert "#" not in result.stdout.splitlines()[0]
