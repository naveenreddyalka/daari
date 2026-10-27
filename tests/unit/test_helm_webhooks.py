"""Helm webhooks.* mounts DAARI_* webhook URL/secret envs (#1959)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "daari"
VALUES = CHART / "values.yaml"


def _helm_template(*set_args: str) -> str:
    cmd = ["helm", "template", "daari", str(CHART), *set_args]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


@pytest.fixture(scope="module")
def helm_available() -> None:
    try:
        subprocess.run(["helm", "version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"helm not available: {exc}")


def test_values_webhooks_block_defaults_empty() -> None:
    values = yaml.safe_load(VALUES.read_text(encoding="utf-8"))
    wh = values["webhooks"]
    for family in (
        "budget",
        "keyExpiry",
        "keyLockout",
        "responsesCompletion",
        "orgIngest",
    ):
        assert family in wh
        assert wh[family].get("url", "") in ("", None)
        secret = wh[family].get("secret") or {}
        assert secret.get("name") in ("", None) or secret == {}


def test_unset_webhooks_render_no_webhook_env(helm_available: None) -> None:
    rendered = _helm_template()
    for name in (
        "DAARI_ALERTS__BUDGET_WEBHOOK_URL",
        "DAARI_ALERTS__BUDGET_WEBHOOK_SECRET",
        "DAARI_ALERTS__KEY_EXPIRY_WEBHOOK_URL",
        "DAARI_ALERTS__KEY_EXPIRY_WEBHOOK_SECRET",
        "DAARI_ALERTS__RESPONSES_COMPLETION_WEBHOOK_URL",
        "DAARI_ALERTS__RESPONSES_COMPLETION_WEBHOOK_SECRET",
        "DAARI_ANTHROPIC__ENFORCEMENT_WEBHOOK_URL",
        "DAARI_ANTHROPIC__ORG_WEBHOOK_SIGNING_SECRET",
    ):
        assert name not in rendered


def test_budget_and_responses_webhook_env_wiring(helm_available: None) -> None:
    rendered = _helm_template(
        "--set",
        "webhooks.budget.url=https://hooks.example/budget",
        "--set",
        "webhooks.budget.secret.name=daari-webhooks",
        "--set",
        "webhooks.budget.secret.key=budget",
        "--set",
        "webhooks.budget.secretPrevious.name=daari-webhooks",
        "--set",
        "webhooks.budget.secretPrevious.key=budget-prev",
        "--set",
        "webhooks.responsesCompletion.url=https://hooks.example/responses",
        "--set",
        "webhooks.responsesCompletion.secret.name=daari-webhooks",
        "--set",
        "webhooks.responsesCompletion.secret.key=responses",
    )
    assert re.search(
        r"name: DAARI_ALERTS__BUDGET_WEBHOOK_URL\s+value: \"https://hooks.example/budget\"",
        rendered,
    )
    assert "DAARI_ALERTS__BUDGET_WEBHOOK_SECRET" in rendered
    assert "DAARI_ALERTS__BUDGET_WEBHOOK_SECRET_PREVIOUS" in rendered
    assert 'key: "budget"' in rendered
    assert 'key: "budget-prev"' in rendered
    assert re.search(
        r"name: DAARI_ALERTS__RESPONSES_COMPLETION_WEBHOOK_URL\s+"
        r'value: "https://hooks.example/responses"',
        rendered,
    )
    assert "DAARI_ALERTS__RESPONSES_COMPLETION_WEBHOOK_SECRET" in rendered
    assert 'name: "daari-webhooks"' in rendered


def test_capacity_helm_docs_mention_webhooks() -> None:
    doc = (
        ROOT / "docs" / "developer" / "guides" / "operations" / "capacity-helm.md"
    ).read_text(encoding="utf-8")
    assert "webhooks:" in doc
    assert "budget" in doc
    assert "secretKeyRef" in doc or "secret.name" in doc
