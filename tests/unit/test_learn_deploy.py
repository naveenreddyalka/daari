"""Phase D deploy: serve fine-tuned adapters (mlx serve / ollama fuse)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.learning.deploy import (
    DEFAULT_TUNED_NAME,
    GGUF_FILENAME,
    DeployError,
    plan_deploy,
    run_deploy,
)


def _make_run(tmp_path, *, status="completed", with_adapters=True):
    run_dir = tmp_path / "20260723-000000"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "model": "mlx-community/Llama-3.2-3B-Instruct-4bit",
                "status": status,
            }
        )
    )
    if with_adapters:
        adapters = run_dir / "adapters"
        adapters.mkdir()
        (adapters / "adapters.safetensors").write_bytes(b"stub")
    return run_dir


class TestPlan:
    def test_mlx_plan_serves_adapter_directly(self, tmp_path):
        run_dir = _make_run(tmp_path)
        plan = plan_deploy(run_dir, backend="mlx", tier="L4")
        assert len(plan.commands) == 1
        command = plan.commands[0]
        assert "server" in command and "--adapter-path" in command
        assert str(run_dir / "adapters") in command
        assert "L4: mlx-community/Llama-3.2-3B-Instruct-4bit" in plan.config_snippet
        assert json.loads((run_dir / "deploy.json").read_text())["status"] == "planned"

    def test_ollama_plan_fuses_then_creates(self, tmp_path):
        run_dir = _make_run(tmp_path)
        plan = plan_deploy(run_dir, backend="ollama", model_name="my-tuned")
        assert [c[3] if len(c) > 3 else c[0] for c in plan.commands[:1]] == ["fuse"]
        assert plan.commands[1][:3] == ["ollama", "create", "my-tuned"]
        modelfile = (run_dir / "Modelfile").read_text()
        assert GGUF_FILENAME in modelfile and modelfile.startswith("FROM ")
        assert "l3: my-tuned" in plan.config_snippet

    def test_rejects_unknown_backend(self, tmp_path):
        with pytest.raises(DeployError, match="unknown backend"):
            plan_deploy(_make_run(tmp_path), backend="vllm")

    def test_rejects_incomplete_run(self, tmp_path):
        run_dir = _make_run(tmp_path, status="failed")
        with pytest.raises(DeployError, match="only completed runs"):
            plan_deploy(run_dir)

    def test_rejects_missing_adapters(self, tmp_path):
        run_dir = _make_run(tmp_path, with_adapters=False)
        with pytest.raises(DeployError, match="no adapters"):
            plan_deploy(run_dir)

    def test_rejects_missing_run_json(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(DeployError, match="no run.json"):
            plan_deploy(empty)


class TestRun:
    def test_mlx_run_refuses_long_running_server(self, tmp_path):
        plan = plan_deploy(_make_run(tmp_path), backend="mlx")
        with pytest.raises(DeployError, match="long-running"):
            run_deploy(plan)

    def test_ollama_run_executes_steps_and_records_status(self, tmp_path, monkeypatch):
        plan = plan_deploy(_make_run(tmp_path), backend="ollama")
        monkeypatch.setattr("daari.learning.deploy._mlx_lm_available", lambda: True)
        monkeypatch.setattr("daari.learning.deploy.shutil.which", lambda _: "/usr/bin/ollama")
        calls = []

        class Result:
            returncode = 0

        monkeypatch.setattr(
            "daari.learning.deploy.subprocess.run", lambda cmd: calls.append(cmd) or Result()
        )
        run_deploy(plan)
        assert len(calls) == 2
        assert json.loads((plan.run_dir / "deploy.json").read_text())["status"] == "completed"

    def test_ollama_run_failure_marks_failed(self, tmp_path, monkeypatch):
        plan = plan_deploy(_make_run(tmp_path), backend="ollama")
        monkeypatch.setattr("daari.learning.deploy._mlx_lm_available", lambda: True)
        monkeypatch.setattr("daari.learning.deploy.shutil.which", lambda _: "/usr/bin/ollama")

        class Result:
            returncode = 1

        monkeypatch.setattr("daari.learning.deploy.subprocess.run", lambda cmd: Result())
        with pytest.raises(DeployError, match="exit code 1"):
            run_deploy(plan)
        assert json.loads((plan.run_dir / "deploy.json").read_text())["status"] == "failed"

    def test_ollama_run_requires_mlx_lm(self, tmp_path, monkeypatch):
        plan = plan_deploy(_make_run(tmp_path), backend="ollama")
        monkeypatch.setattr("daari.learning.deploy._mlx_lm_available", lambda: False)
        with pytest.raises(DeployError, match="mlx-lm is not installed"):
            run_deploy(plan)

    def test_ollama_run_requires_ollama_binary(self, tmp_path, monkeypatch):
        plan = plan_deploy(_make_run(tmp_path), backend="ollama")
        monkeypatch.setattr("daari.learning.deploy._mlx_lm_available", lambda: True)
        monkeypatch.setattr("daari.learning.deploy.shutil.which", lambda _: None)
        with pytest.raises(DeployError, match="ollama binary not found"):
            run_deploy(plan)


class TestCLI:
    def test_mlx_deploy_prints_serve_command_and_snippet(self, tmp_path):
        run_dir = _make_run(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli_app, ["learn", "deploy", str(run_dir)])
        assert result.exit_code == 0
        assert "mlx_lm server" in result.output.replace("-m mlx_lm server", "mlx_lm server")
        assert "long-running" in result.output
        assert "enabled: true" in result.output

    def test_ollama_dry_run_executes_nothing(self, tmp_path):
        run_dir = _make_run(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli_app,
            ["learn", "deploy", str(run_dir), "--backend", "ollama", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert DEFAULT_TUNED_NAME in result.output

    def test_bad_run_dir_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["learn", "deploy", str(tmp_path)])
        assert result.exit_code == 1
