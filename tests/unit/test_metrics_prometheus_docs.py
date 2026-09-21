"""metrics-prometheus.md series table stays contiguous (#679)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs/developer/guides/observability/metrics-prometheus.md"


def test_metrics_prometheus_series_table_is_contiguous() -> None:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| Series |"))
    sep = start + 1
    assert lines[sep].startswith("|---"), lines[sep]
    body: list[str] = []
    for line in lines[sep + 1 :]:
        if not line.startswith("|"):
            break
        body.append(line)
    assert body, "expected series table body rows"
    assert any("daari_rejects_total" in row for row in body)
    assert any("daari_ttft_preference_total" in row for row in body)
    assert any("daari_team_rate_limit_remaining" in row for row in body)
    assert any("daari_tier_shadow_samples_total" in row for row in body)
    assert any("daari_cancelled_requests_total" in row for row in body)
    assert any("daari_request_deadline_exceeded_total" in row for row in body)
    assert any("daari_escalations_total" in row for row in body)
    assert any("daari_errors_total" in row for row in body)
    # Orphaned mid-table prose would end the contiguous body early.
    assert body[-1].startswith("| `daari_escalations_total")

    text = DOC.read_text(encoding="utf-8")
    assert "soft_warnings" in text
    assert "rejects" in text
    assert "backend_summary" in text
    assert "traces-stats.md" in text
    assert "daari_tier_shadow_samples_total" in text
    assert "routing-tiers.md" in text
    assert "daari_escalations_total" in text
    assert "daari_errors_total" in text
    assert "Escalations & errors" in text
    cancelled_row = next(row for row in body if "daari_cancelled_requests_total" in row)
    assert "`tts`" in cancelled_row
    assert "`mcp`" in cancelled_row
