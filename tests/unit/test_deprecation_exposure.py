"""successor_model, doctor copy, and deprecation exposure from the ledger (#2346)."""

from __future__ import annotations

from daari.config.settings import Settings, merged_model_lifecycle
from daari.observability.spend import SpendLedger
from daari.observability.usage import UsageLedger, build_deprecation_exposure
from daari.router.capabilities import anthropic_lifecycle_fields
from daari.setup.doctor import _check_model_lifecycle


def test_merged_lifecycle_keeps_successor_source_and_unknown_fields():
    settings = Settings.model_validate(
        {
            "models": {
                "lifecycle": {
                    "gpt-4o": {
                        "lifecycle": "deprecated",
                        "deprecated_at": "2026-10-14",
                        "retires_at": "2027-01-14",
                        "successor_model": "gpt-6.1-terra",
                        "deprecation_source": "https://example.test/deprecations",
                        "mystery": "kept",
                    }
                }
            }
        }
    )
    row = merged_model_lifecycle(settings)["gpt-4o"]
    assert row["successor_model"] == "gpt-6.1-terra"
    assert row["deprecation_source"] == "https://example.test/deprecations"
    assert row["mystery"] == "kept"
    fields = anthropic_lifecycle_fields("gpt-4o", settings)
    assert fields["lifecycle"] == "deprecated"
    assert fields["successor_model"] == "gpt-6.1-terra"
    assert fields["deprecation_source"] == "https://example.test/deprecations"


def test_doctor_names_successor_on_deprecated_model():
    settings = Settings.model_validate(
        {
            "frontier": {"model": "gpt-4o"},
            "models": {
                "lifecycle": {
                    "gpt-4o": {
                        "lifecycle": "deprecated",
                        "deprecated_at": "2026-10-14",
                        "retires_at": "2027-01-14",
                        "successor_model": "gpt-6.1-terra",
                    }
                }
            },
        }
    )
    result = _check_model_lifecycle(settings)
    assert result.optional is True
    assert "successor: gpt-6.1-terra" in result.detail
    assert "2027-01-14" in result.detail


def test_exposure_from_seeded_spend_ledger_splits_key_and_team(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite")
    ledger.record(
        ts="2026-11-27T12:00:00+00:00",
        key_id="key-a",
        team_id="eng",
        model="gpt-4o",
        request_id="r1",
    )
    ledger.record(
        ts="2026-11-27T12:05:00+00:00",
        key_id="key-b",
        team_id="eng",
        model="gpt-4o",
        request_id="r2",
    )
    ledger.record(
        ts="2026-11-27T12:06:00+00:00",
        key_id="key-a",
        team_id="ops",
        model="gpt-6-luna",
        request_id="r3",
    )
    settings = Settings.model_validate(
        {
            "models": {
                "lifecycle": {
                    "gpt-4o": {
                        "lifecycle": "deprecated",
                        "deprecated_at": "2026-10-14",
                        "retires_at": "2027-01-14",
                        "successor_model": "gpt-6.1-terra",
                        "deprecation_source": "https://example.test/deprecations",
                    }
                }
            }
        }
    )
    rows = ledger.model_key_team_counts(since_iso="2026-11-01T00:00:00+00:00")
    exposure = build_deprecation_exposure(rows, merged_model_lifecycle(settings))
    assert len(exposure) == 1
    row = exposure[0]
    assert row["model"] == "gpt-4o"
    assert row["requests"] == 2
    assert row["successor_model"] == "gpt-6.1-terra"
    assert row["deprecation_source"] == "https://example.test/deprecations"
    assert row["deprecated_at"] == "2026-10-14"
    assert row["by_key"] == [
        {"key_id": "key-a", "requests": 1},
        {"key_id": "key-b", "requests": 1},
    ]
    assert row["by_team"] == [{"team_id": "eng", "requests": 2}]


def test_usage_ledger_client_counts_feed_exposure(tmp_path):
    usage = UsageLedger(tmp_path / "usage.sqlite")
    usage.record(tier="L6", model="gpt-4o-mini", client_id="alice", day="2026-11-27")
    usage.record(tier="L6", model="gpt-4o-mini", client_id="alice", day="2026-11-27")
    rows = usage.model_client_counts(days=7)
    exposure = build_deprecation_exposure(rows, merged_model_lifecycle(Settings()))
    match = next(row for row in exposure if row["model"] == "gpt-4o-mini")
    assert match["requests"] == 2
    assert match["by_key"] == [{"key_id": "alice", "requests": 2}]
    assert match["by_team"] == []
    assert match["retires_at"] == "2027-01-14"
