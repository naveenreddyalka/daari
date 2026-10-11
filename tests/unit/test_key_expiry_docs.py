"""Operator guides document key_expiry webhook + warn_days (#1565)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_key_expiry_alerts_documented_next_to_budget_webhooks() -> None:
    budgets = (
        ROOT / "docs/developer/guides/configuration/budgets-frontier.md"
    ).read_text(encoding="utf-8")
    auth = (
        ROOT / "docs/developer/guides/configuration/auth-and-keys.md"
    ).read_text(encoding="utf-8")
    virtual_keys = (
        ROOT / "docs/developer/guides/features/virtual-keys.md"
    ).read_text(encoding="utf-8")

    assert "key_expiry_webhook_url" in budgets
    assert "key_expiry_webhook_secret" in budgets
    assert "key_expiry_warn_days" in budgets
    assert '"event": "key_expiry"' in budgets or '"event":"key_expiry"' in budgets
    assert "X-Daari-Signature" in budgets
    assert "daari_virtual_keys" in budgets
    assert "daari doctor" in budgets
    assert "key_expiry" in budgets

    assert "key_expiry_webhook_url" in auth or "key_expiry_warn_days" in auth
    assert "daari_virtual_keys" in auth
    assert "budgets-frontier.md" in auth

    assert "key_expiry_webhook_url" in virtual_keys
    assert "key_expiry_warn_days" in virtual_keys
    assert "daari_virtual_keys" in virtual_keys
    assert "event: key_expiry" in virtual_keys or "key_expiry" in virtual_keys
