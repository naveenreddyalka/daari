"""Phase D2b: dataset export in mlx-lm chat format (issue #62)."""

from __future__ import annotations

import json

import pytest

from daari.learning.dataset import DatasetError, export_dataset
from daari.learning.examples import ExampleStore


def _store(tmp_path) -> ExampleStore:
    return ExampleStore(str(tmp_path / "examples.sqlite3"))


def _seed(store: ExampleStore, count: int, *, accepted: int = 0, prefix: str = "t") -> None:
    for i in range(count):
        trace_id = f"{prefix}{i}"
        store.record(
            trace_id=trace_id,
            category="doc_qa",
            complexity="standard",
            tier="L3",
            model="llama3.2:3b",
            messages=[
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": f"question number {i}"},
            ],
            completion=f"answer number {i}",
        )
        if i < accepted:
            store.mark_accepted(trace_id)


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestExportFormat:
    def test_writes_mlx_chat_format(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, 10)
        out = tmp_path / "dataset"

        result = export_dataset(store, out, min_examples=8)

        train = _read_jsonl(out / "train.jsonl")
        valid = _read_jsonl(out / "valid.jsonl")
        assert result["train"] == len(train)
        assert result["valid"] == len(valid)
        assert len(train) + len(valid) == 10
        sample = train[0]
        assert set(sample.keys()) == {"messages"}
        assert sample["messages"][0] == {"role": "system", "content": "be brief"}
        assert sample["messages"][-1]["role"] == "assistant"
        assert sample["messages"][-1]["content"].startswith("answer number")

    def test_split_proportion_and_nonempty_valid(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, 40)
        out = tmp_path / "dataset"

        result = export_dataset(store, out, split=0.9, min_examples=8)

        assert result["train"] + result["valid"] == 40
        assert result["valid"] >= 1, "valid set must never be empty"
        assert result["train"] > result["valid"]

    def test_split_is_deterministic(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, 20)

        first = export_dataset(store, tmp_path / "a", min_examples=8)
        second = export_dataset(store, tmp_path / "b", min_examples=8)

        assert _read_jsonl(tmp_path / "a" / "train.jsonl") == _read_jsonl(
            tmp_path / "b" / "train.jsonl"
        )
        assert first == second


class TestExportFilters:
    def test_only_accepted_filter(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, 20, accepted=10)
        out = tmp_path / "dataset"

        result = export_dataset(store, out, only_accepted=True, min_examples=8)

        assert result["train"] + result["valid"] == 10

    def test_below_min_examples_raises(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, 3)

        with pytest.raises(DatasetError, match="need at least 8"):
            export_dataset(store, tmp_path / "dataset", min_examples=8)

    def test_cli_export(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli.app import app as cli_app
        from daari.config.settings import Settings

        settings = Settings.model_validate(
            {"learning": {"examples_path": str(tmp_path / "examples.sqlite3")}}
        )
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        _seed(_store(tmp_path), 12)

        runner = CliRunner()
        out = tmp_path / "cli-dataset"
        result = runner.invoke(cli_app, ["learn", "export-dataset", "--out", str(out)])

        assert result.exit_code == 0, result.output
        assert (out / "train.jsonl").exists()
        assert (out / "valid.jsonl").exists()

    def test_cli_export_below_min_fails(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli.app import app as cli_app
        from daari.config.settings import Settings

        settings = Settings.model_validate(
            {"learning": {"examples_path": str(tmp_path / "examples.sqlite3")}}
        )
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        _seed(_store(tmp_path), 2)

        runner = CliRunner()
        result = runner.invoke(
            cli_app, ["learn", "export-dataset", "--out", str(tmp_path / "d")]
        )

        assert result.exit_code != 0
        assert "need at least" in result.output
