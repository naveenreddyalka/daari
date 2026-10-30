"""Doctor tip when Ollama lists lfm3-vl but models.l4 is not wired (#2006)."""

from __future__ import annotations

import httpx

from daari.config.settings import Settings
from daari.setup.doctor import _check_lfm3_vl_unused
from daari.setup.models import LFM3_VL_MODEL


def _tags_client(names: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(
                200, json={"models": [{"name": n} for n in names]}
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lfm3_vl_tip_when_host_has_tag_but_l4_elsewhere():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    tip = _check_lfm3_vl_unused(
        settings, _tags_client([LFM3_VL_MODEL, "llama3.1:8b"])
    )
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "ollama_lfm3_vl_unused"
    assert LFM3_VL_MODEL in tip.detail
    assert "daari setup models --lfm3-vl" in tip.detail


def test_lfm3_vl_tip_quiet_when_l4_already_lfm3_vl():
    settings = Settings.model_validate(
        {
            "models": {"l4": LFM3_VL_MODEL},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_lfm3_vl_unused(settings, _tags_client([LFM3_VL_MODEL])) is None


def test_lfm3_vl_tip_quiet_when_tag_absent_on_host():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_lfm3_vl_unused(settings, _tags_client(["llama3.1:8b"])) is None


def test_lfm3_vl_tip_quiet_when_ollama_unreachable():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_lfm3_vl_unused(settings, client) is None
