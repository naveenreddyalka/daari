"""Phase D2c: LoRA fine-tune runner — command construction and gating (issue #63).

CI never trains. These tests pin the plan (command, paths, run.json)
and the guards (min examples, missing mlx-lm), never a real mlx_lm run.
"""

from __future__ import annotations

import json

import pytest

from daari.learning.dataset import DatasetError
from daari.learning.examples import ExampleStore
from daari.learning.finetune import DEFAULT_MODEL, FinetuneError, plan_finetune, run_finetune


def _store(tmp_path) -> ExampleStore:
    store = ExampleStore(str(tmp_path / "examples.sqlite3"))
    for i in range(12):
        store.record(
            trace_id=f"t{i}",
            category="doc_qa",
            complexity="standard",
            tier="L3",
            model="llama3.2:3b",
            messages=[{"role": "user", "content": f"question {i}"}],
            completion=f"answer {i}",
        )
    return store


class TestPlan:
    def test_plan_builds_command_and_run_dir(self, tmp_path):
        store = _store(tmp_path)
        plan = plan_finetune(store, runs_root=tmp_path / "runs", iters=25)

        assert plan.model == DEFAULT_MODEL
        assert plan.counts["train"] + plan.counts["valid"] == 12
        assert plan.counts["valid"] >= 1
        assert (plan.run_dir / "data" / "train.jsonl").exists()
        assert (plan.run_dir / "data" / "valid.jsonl").exists()

        command = plan.command
        assert command[:4] == ["python", "-m", "mlx_lm", "lora"]
        assert "--train" in command
        assert command[command.index("--model") + 1] == DEFAULT_MODEL
        assert command[command.index("--data") + 1] == str(plan.run_dir / "data")
        assert command[command.index("--iters") + 1] == "25"
        assert command[command.index("--adapter-path") + 1] == str(plan.run_dir / "adapters")

    def test_plan_writes_run_json(self, tmp_path):
        store = _store(tmp_path)
        plan = plan_finetune(store, runs_root=tmp_path / "runs", iters=10)

        payload = json.loads((plan.run_dir / "run.json").read_text())
        assert payload["model"] == DEFAULT_MODEL
        assert payload["iters"] == 10
        assert payload["counts"] == plan.counts
        assert payload["command"] == plan.command
        assert payload["status"] == "planned"

    def test_plan_min_examples_gate(self, tmp_path):
        store = ExampleStore(str(tmp_path / "examples.sqlite3"))
        store.record(
            trace_id="only", category="chat", complexity="trivial", tier="L3",
            model="m", messages=[{"role": "user", "content": "q"}], completion="a",
        )

        with pytest.raises(DatasetError, match="need at least"):
            plan_finetune(store, runs_root=tmp_path / "runs", min_examples=8)

    def test_plan_custom_model(self, tmp_path):
        store = _store(tmp_path)
        plan = plan_finetune(store, runs_root=tmp_path / "runs", model="my/model")
        assert plan.command[plan.command.index("--model") + 1] == "my/model"


class TestRun:
    def test_missing_mlx_lm_raises(self, tmp_path, monkeypatch):
        plan = plan_finetune(_store(tmp_path), runs_root=tmp_path / "runs")
        monkeypatch.setattr(
            "daari.learning.finetune._mlx_lm_available", lambda: False
        )

        with pytest.raises(FinetuneError, match="pip install mlx-lm"):
            run_finetune(plan)

    def test_run_invokes_command_and_updates_status(self, tmp_path, monkeypatch):
        plan = plan_finetune(_store(tmp_path), runs_root=tmp_path / "runs")
        monkeypatch.setattr("daari.learning.finetune._mlx_lm_available", lambda: True)
        invoked = {}

        def fake_run(command, **kwargs):
            invoked["command"] = command

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("daari.learning.finetune.subprocess.run", fake_run)
        run_finetune(plan)

        assert invoked["command"] == plan.command
        payload = json.loads((plan.run_dir / "run.json").read_text())
        assert payload["status"] == "completed"

    def test_failed_run_marks_status(self, tmp_path, monkeypatch):
        plan = plan_finetune(_store(tmp_path), runs_root=tmp_path / "runs")
        monkeypatch.setattr("daari.learning.finetune._mlx_lm_available", lambda: True)

        def fake_run(command, **kwargs):
            class Result:
                returncode = 3

            return Result()

        monkeypatch.setattr("daari.learning.finetune.subprocess.run", fake_run)
        with pytest.raises(FinetuneError, match="exit code 3"):
            run_finetune(plan)

        payload = json.loads((plan.run_dir / "run.json").read_text())
        assert payload["status"] == "failed"


class TestCli:
    def _settings(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings.model_validate(
            {"learning": {"examples_path": str(tmp_path / "examples.sqlite3")}}
        )
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    def test_dry_run_prints_command_without_running(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli.app import app as cli_app

        self._settings(tmp_path, monkeypatch)
        _store(tmp_path)
        monkeypatch.setattr(
            "daari.learning.finetune.subprocess.run",
            lambda *a, **k: pytest.fail("dry-run must not execute"),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli_app,
            ["learn", "finetune", "--dry-run", "--runs-root", str(tmp_path / "runs")],
        )

        assert result.exit_code == 0, result.output
        assert "mlx_lm lora" in result.output
        assert "train /" in result.output
        assert "Dry run — nothing executed" in result.output

    def test_cli_too_few_examples_fails_cleanly(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli.app import app as cli_app

        self._settings(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(
            cli_app,
            ["learn", "finetune", "--dry-run", "--runs-root", str(tmp_path / "runs")],
        )

        assert result.exit_code != 0
        assert "need at least" in result.output
