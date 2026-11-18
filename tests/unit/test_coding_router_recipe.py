"""Hermetic pin: coding-router tutorial + doctor incomplete-compose tip (#2238)."""

from __future__ import annotations

from pathlib import Path

import yaml

from daari.config.settings import Settings, SignalOverrideRule
from daari.setup.doctor import _check_coding_router_compose, run_doctor

ROOT = Path(__file__).resolve().parents[2]
TUTORIAL = ROOT / "docs/developer/tutorials/coding-router.md"
COMPARE = ROOT / "docs/developer/resources/compare-openrouter.md"


def _extract_yaml_fence(text: str) -> str:
    start = text.find("```yaml")
    assert start >= 0, "tutorial must include a ```yaml example"
    rest = text[start + len("```yaml") :]
    end = rest.find("```")
    assert end >= 0
    return rest[:end].strip()


def test_coding_router_tutorial_exists_and_parses() -> None:
    assert TUTORIAL.is_file()
    text = TUTORIAL.read_text(encoding="utf-8")
    lower = text.lower()
    assert "virtual_models" in text
    assert "virtual_model_selection" in text
    assert "cost" in lower
    assert "signal_overrides" in text
    assert "code_gen" in text or "category: code" in text
    assert "reasoning_effort" in text
    assert "virtual_model_latency_slo_ms" in text

    snippet = _extract_yaml_fence(text)
    loaded = yaml.safe_load(snippet)
    assert isinstance(loaded, dict)
    settings = Settings.model_validate(loaded)
    routing = settings.routing
    assert routing.virtual_models
    assert routing.virtual_model_selection == "cost"
    assert routing.signal_overrides
    codeish = False
    for rule in routing.signal_overrides:
        match_cat = (rule.match or {}).get("category")
        if match_cat in {"code", "code_gen", "code_explain"}:
            codeish = True
            assert rule.reasoning_effort is not None
    assert codeish
    assert any(
        name in routing.virtual_model_latency_slo_ms for name in routing.virtual_models
    )


def test_compare_openrouter_links_coding_router_tutorial() -> None:
    text = COMPARE.read_text(encoding="utf-8")
    section_start = text.find("## Auto Router and Auto Code")
    assert section_start >= 0
    nxt = text.find("\n## ", section_start + 1)
    section = text[section_start:] if nxt < 0 else text[section_start:nxt]
    assert "coding-router" in section
    assert "tutorials/coding-router.md" in section


def test_doctor_tips_code_signal_without_virtual_models(settings: Settings) -> None:
    settings.routing.virtual_models = {}
    settings.routing.signal_overrides = [
        SignalOverrideRule(
            id="code-effort",
            match={"category": "code_gen"},
            reasoning_effort="high",
        )
    ]
    tip = _check_coding_router_compose(settings)
    assert tip is not None
    assert tip.name == "coding_router_compose"
    assert tip.optional is True
    assert tip.ok is True
    detail = tip.detail.lower()
    assert "virtual_models" in detail
    assert "code" in detail
    assert "coding-router" in detail or "tutorial" in detail


def test_doctor_quiet_when_virtual_models_present(settings: Settings) -> None:
    settings.routing.virtual_models = {"coding": ["L4", "openai/gpt-4o-mini"]}
    settings.routing.signal_overrides = [
        SignalOverrideRule(
            id="code-effort",
            match={"category": "code_gen"},
            reasoning_effort="medium",
        )
    ]
    assert _check_coding_router_compose(settings) is None


def test_doctor_quiet_without_code_signal_overrides(settings: Settings) -> None:
    settings.routing.virtual_models = {}
    settings.routing.signal_overrides = [
        SignalOverrideRule(
            id="img-doc",
            match={"has_images": True},
            category="doc_qa",
        )
    ]
    assert _check_coding_router_compose(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "coding_router_compose" for r in rows)
