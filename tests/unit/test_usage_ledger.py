"""Unit tests for the persistent usage ledger (issue #14)."""

from __future__ import annotations

from daari.observability.usage import UsageLedger


def test_record_accumulates_per_day_and_tier(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    ledger.record(tier="L3", cache_hit=False, prompt_chars=400, completion_chars=200, day="2026-07-10")
    ledger.record(tier="L3", cache_hit=False, prompt_chars=100, completion_chars=100, day="2026-07-10")
    ledger.record(tier="L0", cache_hit=True, prompt_chars=400, completion_chars=200, day="2026-07-10")
    ledger.record(tier="L3", cache_hit=False, prompt_chars=50, completion_chars=50, day="2026-07-09")

    report = ledger.report(days=365, frontier_price_per_1k_tokens=0.002)

    assert report["enabled"] is True
    by_day = {entry["day"]: entry for entry in report["days"]}
    assert by_day["2026-07-10"]["requests"] == 3
    assert by_day["2026-07-10"]["cache_hits"] == 1
    assert by_day["2026-07-10"]["tiers"]["L3"]["requests"] == 2
    assert by_day["2026-07-10"]["tiers"]["L3"]["prompt_chars"] == 500
    assert by_day["2026-07-09"]["requests"] == 1
    assert report["totals"]["requests"] == 4
    assert report["totals"]["cache_hits"] == 1


def test_savings_exclude_frontier_tier(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    # 4000 local chars -> 1000 tokens -> 1k tokens * $0.002 = $0.002 saved.
    ledger.record(tier="L3", prompt_chars=3000, completion_chars=1000, day="2026-07-10")
    # Frontier traffic saves nothing.
    ledger.record(tier="L6", prompt_chars=8000, completion_chars=8000, day="2026-07-10")

    totals = ledger.report(days=365, frontier_price_per_1k_tokens=0.002)["totals"]

    assert totals["local_requests"] == 1
    assert totals["frontier_requests"] == 1
    assert totals["estimated_saved_usd"] == 0.002


def test_report_window_filters_old_days(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    ledger.record(tier="L3", prompt_chars=10, completion_chars=10, day="2000-01-01")

    report = ledger.report(days=7)

    assert report["days"] == []
    assert report["totals"]["requests"] == 0


def test_disabled_ledger_is_noop(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3", enabled=False)
    ledger.record(tier="L3", prompt_chars=10, completion_chars=10)

    report = ledger.report(days=7)

    assert report["enabled"] is False
    assert report["days"] == []
    assert not (tmp_path / "ledger.sqlite3").exists()


def test_record_never_raises_on_bad_path():
    ledger = UsageLedger(path="/dev/null/impossible/ledger.sqlite3")
    ledger.record(tier="L3", prompt_chars=10, completion_chars=10)
    report = ledger.report(days=7)
    assert report["days"] == []
