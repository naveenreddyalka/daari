from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.config.settings import Settings
from daari.setup.onboard import (
    OLLAMA_DOWNLOAD_URL,
    OnboardReport,
    default_onboard_models,
    run_onboard,
)


@pytest.fixture
def settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b", "l4": "llama3.1:8b", "l5": "llama3.1:70b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {
                    "enabled": True,
                    "path": str(tmp_path / "l1"),
                    "embedding_model": "nomic-embed-text",
                },
            },
        }
    )


class TestDefaultOnboardModels:
    def test_default_is_l3_and_embed(self, settings):
        assert default_onboard_models(settings) == ["llama3.2:3b", "nomic-embed-text"]

    def test_minimal_is_l3_only(self, settings):
        assert default_onboard_models(settings, minimal=True) == ["llama3.2:3b"]

    def test_optional_l4_l5(self, settings):
        assert default_onboard_models(settings, pull_l4=True, pull_l5=True) == [
            "llama3.2:3b",
            "nomic-embed-text",
            "llama3.1:8b",
            "llama3.1:70b",
        ]


class TestRunOnboard:
    def test_unreachable_ollama_includes_download_url(self, settings):
        def boom() -> list[str]:
            raise ConnectionError("connection refused")

        report = run_onboard(
            settings,
            fetch_models_fn=boom,
            pull_fn=lambda _model: True,
            doctor_fn=lambda *_a, **_k: [],
        )
        ollama = report.step("ollama")
        assert ollama is not None
        assert ollama.ok is False
        assert OLLAMA_DOWNLOAD_URL in ollama.detail
        assert report.ready is False
        assert report.pulled == []

    def test_pulls_missing_l3_and_embed(self, settings):
        pulled: list[str] = []

        report = run_onboard(
            settings,
            fetch_models_fn=lambda: [],
            pull_fn=lambda model: pulled.append(model) or True,
            doctor_fn=lambda *_a, **_k: [],
        )
        assert pulled == ["llama3.2:3b", "nomic-embed-text"]
        assert report.pulled == pulled
        assert report.step("ollama") is not None
        assert report.step("ollama").ok is True

    def test_skips_models_already_present(self, settings):
        pulled: list[str] = []

        report = run_onboard(
            settings,
            fetch_models_fn=lambda: ["llama3.2:3b", "nomic-embed-text:latest"],
            pull_fn=lambda model: pulled.append(model) or True,
            doctor_fn=lambda *_a, **_k: [],
        )
        assert pulled == []
        assert report.skipped == ["llama3.2:3b", "nomic-embed-text"]

    def test_no_pull_skips_ollama_pulls(self, settings):
        pulled: list[str] = []

        run_onboard(
            settings,
            pull=False,
            fetch_models_fn=lambda: [],
            pull_fn=lambda model: pulled.append(model) or True,
            doctor_fn=lambda *_a, **_k: [],
        )
        assert pulled == []

    def test_does_not_look_for_install_sh(self, settings):
        source = Path(__file__).resolve().parents[2] / "daari" / "setup" / "onboard.py"
        assert "install.sh" not in source.read_text(encoding="utf-8")

        run_onboard(
            settings,
            fetch_models_fn=lambda: ["llama3.2:3b", "nomic-embed-text"],
            pull_fn=lambda _model: True,
            doctor_fn=lambda *_a, **_k: [],
        )

    def test_failed_pull_marks_not_ready(self, settings):
        report = run_onboard(
            settings,
            fetch_models_fn=lambda: [],
            pull_fn=lambda _model: False,
            doctor_fn=lambda *_a, **_k: [],
        )
        assert report.ready is False
        assert report.pulled == []

    def test_calls_doctor_module_when_fn_omitted(self, settings, monkeypatch):
        called = {"doctor": False}

        def fake_doctor(*_a, **_k):
            called["doctor"] = True
            return []

        monkeypatch.setattr("daari.setup.onboard.run_doctor_checks", fake_doctor)
        run_onboard(
            settings,
            fetch_models_fn=lambda: ["llama3.2:3b", "nomic-embed-text"],
            pull_fn=lambda _model: True,
        )
        assert called["doctor"] is True

    def test_next_steps_include_serve(self, settings):
        report = run_onboard(
            settings,
            fetch_models_fn=lambda: ["llama3.2:3b", "nomic-embed-text"],
            pull_fn=lambda _model: True,
            doctor_fn=lambda *_a, **_k: [],
        )
        assert any(step == "daari serve" for step in report.next_steps)

    def test_start_serve_runs_when_ready(self, settings):
        called = {"serve": False}

        report = run_onboard(
            settings,
            start_serve=True,
            fetch_models_fn=lambda: ["llama3.2:3b", "nomic-embed-text"],
            pull_fn=lambda _model: True,
            doctor_fn=lambda *_a, **_k: [],
            serve_fn=lambda: called.__setitem__("serve", True) or True,
        )
        assert called["serve"] is True
        assert report.served is True
        assert report.step("serve") is not None
        assert report.step("serve").ok is True
        assert "11435" in report.step("serve").detail
        assert "daari serve" not in report.next_steps

    def test_start_serve_skipped_when_not_ready(self, settings):
        called = {"serve": False}

        report = run_onboard(
            settings,
            start_serve=True,
            fetch_models_fn=lambda: (_ for _ in ()).throw(ConnectionError("down")),
            pull_fn=lambda _model: True,
            doctor_fn=lambda *_a, **_k: [],
            serve_fn=lambda: called.__setitem__("serve", True) or True,
        )
        assert called["serve"] is False
        assert report.served is False
        assert report.ready is False


class TestOnboardCli:
    def test_onboard_command_forwards_flags(self, settings, monkeypatch):
        captured: dict = {}

        def fake_onboard(*_args, **kwargs):
            captured.update(kwargs)
            return OnboardReport(
                steps=[],
                pulled=[],
                skipped=[],
                next_steps=["daari serve"],
                ready=True,
            )

        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr("daari.cli.app.run_onboard", fake_onboard)

        result = CliRunner().invoke(
            app, ["onboard", "--yes", "--no-pull", "--no-run-doctor", "--minimal", "--serve"]
        )
        assert result.exit_code == 0, result.output
        assert captured["pull"] is False
        assert captured["run_doctor"] is False
        assert captured["minimal"] is True
        assert captured["start_serve"] is True
        assert "daari serve" in result.stdout

    def test_onboard_exits_nonzero_when_not_ready(self, settings, monkeypatch):
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr(
            "daari.cli.app.run_onboard",
            lambda *_a, **_k: OnboardReport(
                steps=[],
                pulled=[],
                skipped=[],
                next_steps=[],
                ready=False,
            ),
        )
        result = CliRunner().invoke(app, ["onboard", "--yes"])
        assert result.exit_code == 1


class TestInstallFallback:
    def test_install_delegates_to_onboard_when_script_missing(self, settings, monkeypatch):
        captured: dict = {}
        orig = Path.is_file

        def fake_is_file(self: Path) -> bool:
            if self.name == "install.sh" and self.parent.name == "scripts":
                return False
            return orig(self)

        def fake_onboard(*_args, **kwargs):
            captured.update(kwargs)
            return OnboardReport(
                steps=[],
                pulled=["llama3.2:3b"],
                skipped=[],
                next_steps=["daari serve"],
                ready=True,
            )

        monkeypatch.setattr(Path, "is_file", fake_is_file)
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr("daari.cli.app.run_onboard", fake_onboard)

        ran = {"subprocess": False}

        def boom(*_a, **_k):
            ran["subprocess"] = True
            raise AssertionError("install.sh must not run when missing")

        monkeypatch.setattr("daari.cli.app.subprocess.run", boom)

        result = CliRunner().invoke(app, ["install", "--no-run-doctor"])
        assert result.exit_code == 0, result.output
        assert ran["subprocess"] is False
        assert captured.get("run_doctor") is False
        assert "daari serve" in result.stdout
