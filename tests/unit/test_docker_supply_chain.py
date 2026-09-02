"""Supply-chain hardening of the ghcr image workflow (issue #295).

Enterprises reviewing daari ask for three things of a published image:
a cosign signature, an SBOM, and a provenance attestation. These tests pin
the docker workflow to that contract so a refactor cannot silently drop it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docker.yml"


def _load():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _build_job():
    return _load()["jobs"]["build"]


def _steps():
    return _build_job()["steps"]


def _step_by_name(fragment: str):
    for step in _steps():
        if fragment.lower() in (step.get("name") or "").lower():
            return step
    return None


def test_id_token_write_is_scoped_to_the_build_job_only():
    data = _load()
    workflow_permissions = data.get("permissions") or {}
    assert workflow_permissions.get("id-token") is None, (
        "id-token: write must not be workflow-wide"
    )
    job_permissions = _build_job().get("permissions") or {}
    assert job_permissions.get("id-token") == "write"
    assert job_permissions.get("packages") == "write"


def test_cosign_keyless_signing_on_push_only():
    installer = next(
        (s for s in _steps() if "cosign-installer" in (s.get("uses") or "")), None
    )
    assert installer is not None, "sigstore/cosign-installer step missing"
    assert "pull_request" in (installer.get("if") or ""), "installer must skip PR builds"

    sign = _step_by_name("sign image")
    assert sign is not None, "cosign sign step missing"
    assert "pull_request" in (sign.get("if") or ""), "signing must skip PR builds"
    run = sign.get("run") or ""
    assert "cosign sign" in run
    assert "--yes" in run
    assert "digest" in run.lower(), "sign by digest so every tag is covered"


def test_build_attaches_sbom_and_provenance():
    build = next(
        (s for s in _steps() if "build-push-action" in (s.get("uses") or "")), None
    )
    assert build is not None
    with_args = build.get("with") or {}
    assert with_args.get("sbom") is True
    assert with_args.get("provenance") is True
    assert build.get("id"), "build step needs an id to expose the pushed digest"


def test_pr_builds_still_do_not_push():
    build = next(s for s in _steps() if "build-push-action" in (s.get("uses") or ""))
    assert "pull_request" in str((build.get("with") or {}).get("push"))


def test_verify_instructions_documented():
    doc = (
        REPO_ROOT / "docs" / "developer" / "guides" / "operations" / "docker-compose.md"
    ).read_text(encoding="utf-8")
    assert "cosign verify" in doc
    assert "--certificate-identity-regexp" in doc
    assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in doc
