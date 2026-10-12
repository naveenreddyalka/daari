"""daari vs LiteLLM comparison (issue #214) — pure-logic tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_vs_litellm.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("bench_vs_litellm", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    return [
        {
            "id": "GP-01",
            "litellm_ms": 900.0,
            "daari_ms": 850.0,
            "daari_tier": "L3",
            "frontier_usd": 0.00075,
        },
        {
            "id": "GP-05",
            "litellm_ms": 800.0,
            "daari_ms": 10.0,
            "daari_tier": "L0",
            "frontier_usd": 0.000625,
        },
        {
            "id": "GP-08",
            "litellm_ms": 5000.0,
            "daari_ms": None,
            "daari_tier": "excluded",
            "frontier_usd": None,
        },
    ]


def test_aggregate_ratios(bench):
    agg = bench.aggregate(_rows())
    # All served: 900/850 and 800/10 → median of 1.06 and 80.
    assert agg["served"] == 2
    assert agg["cache_hit_rows"] == 1
    assert agg["cache_hit_speedup_median"] == pytest.approx(80.0)
    assert agg["overall_speedup_median"] == pytest.approx((900 / 850 + 80) / 2, rel=0.01)
    assert agg["frontier_usd_total"] == pytest.approx(0.001375)
    assert agg["zero_cost_rate"] == pytest.approx(1.0)


def test_render_joins_by_prompt_id(bench):
    report = {
        "date": "2026-08-21",
        "commit": "abc1234",
        "hardware": "Apple M4 Pro, 48 GB RAM",
        "ollama_version": "0.18.2",
        "model": "llama3.2:3b",
        "litellm_version": "1.2.3",
        "rows": _rows(),
        "judgment_rows": [
            {
                "id": "DEC-01",
                "path": "/v1/decisions",
                "litellm_ms": None,
                "daari_ms": 42.0,
                "note": "LiteLLM build lacks /v1/decisions",
            },
            {
                "id": "SYS-01",
                "path": "/v1/systemone",
                "litellm_ms": 120.0,
                "daari_ms": 40.0,
                "note": "",
            },
        ],
        **bench.aggregate(_rows()),
    }
    text = bench.render_markdown(report)
    assert "GP-01" in text and "GP-05" in text and "GP-08" in text
    assert "LiteLLM" in text
    assert "abc1234" in text
    assert "priced" in text.lower() or "implied" in text.lower()
    assert "## Decisions / System One" in text
    assert "DEC-01" in text and "SYS-01" in text
    assert "/v1/decisions" in text and "/v1/systemone" in text
    assert "3.00x" in text
    assert "LiteLLM build lacks /v1/decisions" in text


def test_judgment_corpus_has_decisions_and_systemone(bench):
    rows = bench.load_judgment_corpus()
    kinds = {row["kind"] for row in rows}
    paths = {row["path"] for row in rows}
    assert "decisions" in kinds
    assert "systemone" in kinds
    assert "/v1/decisions" in paths
    assert "/v1/systemone" in paths
    assert bench.judgment_path({"kind": "decisions"}) == "/v1/decisions"
    assert bench.judgment_path({"kind": "systemone"}) == "/v1/systemone"
    assert bench.judgment_path({"path": "/v1/decisions"}) == "/v1/decisions"


def test_post_json_path_skips_404(bench, monkeypatch):
    class _Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 should not raise_for_status")

        def json(self):
            return {"error": "not found"}

    monkeypatch.setattr(bench.httpx, "post", lambda *a, **k: _Resp())
    result = bench.post_json_path(
        "http://peer.test",
        "/v1/decisions",
        {
            "model": "nimble",
            "input": "x",
            "questions": [{"type": "boolean", "name": "ok", "instructions": "y"}],
        },
        timeout=1.0,
    )
    assert result["skipped"] is True
    assert result["ok"] is False
    assert "lacks" in result["error"]


def test_run_judgment_notes_missing_litellm_route(bench, monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_post(base_url, path, body, timeout, **_kwargs):
        calls.append((base_url, path))
        if "litellm" in base_url:
            return {"ok": False, "skipped": True, "error": f"peer lacks {path}", "ms": 1.0}
        return {"ok": True, "skipped": False, "ms": 25.0}

    monkeypatch.setattr(bench, "post_json_path", fake_post)
    rows = bench.run_judgment(
        "http://litellm.test",
        "http://daari.test",
        1.0,
        model="nimble",
        corpus=bench.JUDGMENT_CORPUS,
    )
    assert len(rows) == 2
    assert {r["path"] for r in rows} == {"/v1/decisions", "/v1/systemone"}
    assert all(r["daari_ms"] == 25.0 for r in rows)
    assert all(r["litellm_ms"] is None for r in rows)
    assert all("LiteLLM build lacks" in r["note"] for r in rows)
    assert ("http://litellm.test", "/v1/decisions") in calls
    assert ("http://daari.test", "/v1/systemone") in calls


def test_main_skips_without_ollama(bench, capsys):
    rc = bench.main(["--ollama", "http://127.0.0.1:9", "--no-write"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out


def test_main_skips_without_litellm_when_unspawnable(bench, capsys, monkeypatch):
    monkeypatch.setattr(bench, "litellm_available", lambda: False)
    monkeypatch.setattr(bench, "ollama_version", lambda _url: "0.18.2")
    rc = bench.main(["--no-spawn", "--no-write"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out


@pytest.mark.benchmark
def test_live_vs_litellm_end_to_end(bench, tmp_path):
    rc = bench.main(["--out", str(tmp_path / "vs-litellm.md")])
    assert rc == 0
