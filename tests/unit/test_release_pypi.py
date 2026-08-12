"""Guided PyPI publish helper (issue #160).

The network and `gh` calls are thin wrappers exercised by running the script for
real; these tests pin the logic that decides *what* to publish, where a mistake
means uploading the wrong ref or a version that can never be replaced.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "release_pypi", REPO_ROOT / "scripts" / "release_pypi.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_pypi"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return _load_module()


def test_version_comes_from_pyproject(module):
    """The published version must track pyproject, never a hardcoded string."""
    assert module.project_version() == module.re.search(
        r'^version\s*=\s*"([^"]+)"',
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        module.re.MULTILINE,
    ).group(1)


def test_publisher_claims_match_the_workflow(module):
    """A claim mismatch is exactly what failed three releases, so pin the values."""
    workflow = (REPO_ROOT / ".github" / "workflows" / module.WORKFLOW).read_text(
        encoding="utf-8"
    )
    assert "environment: pypi" in workflow, "the hint prints environment `pypi`"
    assert module.OWNER == "naveenreddyalka"
    assert module.REPO == "daari"


def test_publish_refuses_a_version_already_on_the_index(module, monkeypatch, capsys):
    """PyPI uploads are immutable; re-publishing must fail before touching CI."""
    monkeypatch.setattr(module, "project_version", lambda: "1.2.0")
    monkeypatch.setattr(module, "published_versions", lambda index="pypi": {"1.2.0"})

    def explode(*args, **kwargs):
        raise AssertionError("must not invoke gh when the version already exists")

    monkeypatch.setattr(module, "run", explode)
    args = module.argparse.Namespace(target="pypi")
    assert module.cmd_publish(args) == 1
    assert "cannot be replaced" in capsys.readouterr().out


def test_missing_project_on_index_reads_as_no_versions(module, monkeypatch):
    """A 404 means "not published yet", not an error to propagate."""

    class NotFound(module.urllib.error.HTTPError):
        def __init__(self):
            super().__init__("url", 404, "Not Found", {}, None)

    def raise_404(*args, **kwargs):
        raise NotFound()

    monkeypatch.setattr(module.urllib.request, "urlopen", raise_404)
    assert module.published_versions("pypi") == set()


def test_cli_exposes_the_three_documented_commands(module, capsys):
    """The docstring and RELEASING.md both promise check/publish/verify."""
    with pytest.raises(SystemExit):
        module.main(["nonsense-command"])
    assert "invalid choice" in capsys.readouterr().err

    with pytest.raises(SystemExit) as exc:
        module.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    for command in ("check", "publish", "verify"):
        assert command in help_text


def test_publish_only_accepts_known_targets(module, capsys):
    with pytest.raises(SystemExit):
        module.main(["publish", "--target", "internal-mirror"])
    assert "invalid choice" in capsys.readouterr().err
