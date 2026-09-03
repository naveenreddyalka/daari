"""Issue auto-labeler (issue #330).

The prd-cycle automation cannot label issues, so every issue it files starts
with an "**Intended labels:**" line. `scripts/apply_intended_labels.py` runs
from a GitHub Actions workflow with the repo token and applies those labels —
allowlisted names only, never creating labels, never `agent:working`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "apply_intended_labels", REPO_ROOT / "scripts" / "apply_intended_labels.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["apply_intended_labels"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


class TestParse:
    def test_happy_path(self, mod):
        body = "**Intended labels: `auto-dev`, `P2`**\n\n## Context\n..."
        assert mod.parse_intended_labels(body) == ["auto-dev", "P2"]

    def test_colon_outside_bold(self, mod):
        body = "**Intended labels:** auto-dev, P1\nrest"
        assert mod.parse_intended_labels(body) == ["auto-dev", "P1"]

    def test_tolerates_whitespace_backticks_and_case(self, mod):
        body = "  **intended   Labels :**   ` auto-dev ` ,`P3`  ,  bug \r\n"
        assert mod.parse_intended_labels(body) == ["auto-dev", "P3", "bug"]

    def test_only_first_line_is_read(self, mod):
        body = "Some intro\n**Intended labels: `auto-dev`, `P1`**"
        assert mod.parse_intended_labels(body) == []

    def test_missing_or_malformed_is_empty(self, mod):
        assert mod.parse_intended_labels("") == []
        assert mod.parse_intended_labels(None) == []
        assert mod.parse_intended_labels("## Context\nno labels here") == []
        assert mod.parse_intended_labels("**Intended labels:**") == []

    def test_dedupes_preserving_order(self, mod):
        assert mod.parse_intended_labels("**Intended labels: P2, auto-dev, P2**") == [
            "P2",
            "auto-dev",
        ]


class TestAllowlist:
    def test_non_allowlisted_names_are_skipped(self, mod):
        wanted, skipped = mod.select_labels(["auto-dev", "P2", "urgent", "wontfix"])
        assert wanted == ["auto-dev", "P2"]
        assert skipped == ["urgent", "wontfix"]

    def test_agent_working_is_never_applied(self, mod):
        wanted, skipped = mod.select_labels(["agent:working", "auto-dev"])
        assert wanted == ["auto-dev"]
        assert skipped == ["agent:working"]

    def test_allowlist_contents(self, mod):
        assert set(mod.ALLOWED_LABELS) == {
            "auto-dev",
            "P1",
            "P2",
            "P3",
            "bug",
            "regression",
            "documentation",
            "enhancement",
        }
        assert "agent:working" not in mod.ALLOWED_LABELS


class FakeApi:
    def __init__(self, existing: list[str]) -> None:
        self.existing = list(existing)
        self.added: list[list[str]] = []

    def current_labels(self, number: int) -> list[str]:
        return list(self.existing)

    def add_labels(self, number: int, labels: list[str]) -> None:
        self.added.append(list(labels))
        self.existing.extend(labels)


class TestApply:
    def test_applies_missing_allowlisted_labels_only(self, mod):
        api = FakeApi(existing=["P2"])
        body = "**Intended labels: `auto-dev`, `P2`, `agent:working`, `urgent`**\n"
        result = mod.apply_intended_labels(42, body, api=api)
        assert api.added == [["auto-dev"]]
        assert result.applied == ["auto-dev"]
        assert result.already_present == ["P2"]
        assert set(result.skipped) == {"agent:working", "urgent"}

    def test_idempotent_when_everything_present(self, mod):
        api = FakeApi(existing=["auto-dev", "P1"])
        result = mod.apply_intended_labels(7, "**Intended labels: auto-dev, P1**", api=api)
        assert api.added == []
        assert result.applied == []

    def test_no_intended_line_is_a_noop(self, mod):
        api = FakeApi(existing=[])
        result = mod.apply_intended_labels(7, "## Context\nplain issue", api=api)
        assert api.added == []
        assert result.applied == [] and result.skipped == []

    def test_never_creates_labels(self, mod):
        # The only mutation the API surface offers is add_labels on an issue;
        # there is deliberately no create-label path.
        assert not hasattr(mod.GitHubApi, "create_label")
        assert mod.GitHubApi.add_labels.__doc__ is not None


class TestCli:
    def test_event_payload_path(self, mod, tmp_path, monkeypatch):
        payload = tmp_path / "event.json"
        payload.write_text(
            json.dumps({"issue": {"number": 99, "body": "**Intended labels: `bug`**"}}),
            encoding="utf-8",
        )
        calls: list = []

        class Api:
            def current_labels(self, number):
                calls.append(("get", number))
                return []

            def add_labels(self, number, labels):
                calls.append(("add", number, labels))

        monkeypatch.setattr(mod, "GitHubApi", lambda: Api())
        assert mod.main(["--event", str(payload)]) == 0
        assert calls == [("get", 99), ("add", 99, ["bug"])]

    def test_issue_number_fetches_body(self, mod, monkeypatch):
        calls: list = []

        class Api:
            def issue_body(self, number):
                calls.append(("body", number))
                return "**Intended labels: `P3`, `auto-dev`**"

            def current_labels(self, number):
                return ["P3"]

            def add_labels(self, number, labels):
                calls.append(("add", number, labels))

        monkeypatch.setattr(mod, "GitHubApi", lambda: Api())
        assert mod.main(["--issue", "12"]) == 0
        assert calls == [("body", 12), ("add", 12, ["auto-dev"])]

    def test_event_without_issue_exits_zero(self, mod, tmp_path, monkeypatch):
        payload = tmp_path / "event.json"
        payload.write_text(json.dumps({"action": "opened"}), encoding="utf-8")
        monkeypatch.setattr(mod, "GitHubApi", lambda: pytest.fail("must not call GitHub"))
        assert mod.main(["--event", str(payload)]) == 0


class TestWorkflowFile:
    """The one workflow file #330 explicitly authorizes."""

    def test_workflow_has_minimal_permissions_and_triggers(self):
        import yaml

        path = REPO_ROOT / ".github" / "workflows" / "issue-labeler.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        # PyYAML parses the bare `on` key as boolean True.
        triggers = data.get("on") or data.get(True)
        assert set(triggers["issues"]["types"]) == {"opened", "edited"}
        assert data["permissions"] == {"issues": "write"}
        steps = data["jobs"]["label"]["steps"]
        run_steps = [s for s in steps if "run" in s]
        assert any("apply_intended_labels.py" in s["run"] for s in run_steps)
        assert all("GITHUB_TOKEN" in json.dumps(s.get("env", {})) for s in run_steps)
