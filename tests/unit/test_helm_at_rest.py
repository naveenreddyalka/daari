"""Helm security.atRestKeySecret mounts DAARI_SECURITY__AT_REST_KEY (#1977)."""

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


def test_values_security_at_rest_secrets_default_empty() -> None:
    values = yaml.safe_load(VALUES.read_text(encoding="utf-8"))
    security = values["security"]
    assert security["atRestKeySecret"] == {}
    assert security["atRestKeyPreviousSecret"] == {}
    comment = VALUES.read_text(encoding="utf-8")
    assert "previous" in comment.lower()
    assert "re-seal" in comment or "reseal" in comment or "roll" in comment


def test_unset_at_rest_secrets_render_no_env(helm_available: None) -> None:
    rendered = _helm_template()
    assert "DAARI_SECURITY__AT_REST_KEY" not in rendered
    assert "DAARI_SECURITY__AT_REST_KEY_PREVIOUS" not in rendered


def test_at_rest_key_secret_env_wiring(helm_available: None) -> None:
    rendered = _helm_template(
        "--set",
        "security.atRestKeySecret.name=daari-at-rest",
        "--set",
        "security.atRestKeySecret.key=current",
        "--set",
        "security.atRestKeyPreviousSecret.name=daari-at-rest",
        "--set",
        "security.atRestKeyPreviousSecret.key=previous",
    )
    assert "DAARI_SECURITY__AT_REST_KEY" in rendered
    assert "DAARI_SECURITY__AT_REST_KEY_PREVIOUS" in rendered
    assert 'name: "daari-at-rest"' in rendered
    assert 'key: "current"' in rendered
    assert 'key: "previous"' in rendered
    assert re.search(
        r"name: DAARI_SECURITY__AT_REST_KEY\s+valueFrom:\s+secretKeyRef:",
        rendered,
    )
    assert re.search(
        r"name: DAARI_SECURITY__AT_REST_KEY_PREVIOUS\s+valueFrom:\s+secretKeyRef:",
        rendered,
    )


def test_capacity_helm_docs_mention_at_rest_key_secret() -> None:
    doc = (
        ROOT / "docs" / "developer" / "guides" / "operations" / "capacity-helm.md"
    ).read_text(encoding="utf-8")
    assert "atRestKeySecret" in doc
    assert "DAARI_SECURITY__AT_REST_KEY" in doc
