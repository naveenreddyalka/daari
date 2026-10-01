"""Doctor tip when OCR base_url and vision_model are unset (#1276)."""

from __future__ import annotations

from daari.setup.doctor import _check_ocr, run_doctor


def test_ocr_tip_when_both_unset(settings):
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    result = _check_ocr(settings)
    assert result.name == "ocr"
    assert not result.ok
    assert result.optional
    assert "ocr.base_url" in result.detail
    assert "ocr.vision_model" in result.detail
    assert "/v1/ocr" in result.detail


def test_ocr_ok_when_base_url_set(settings):
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.vision_model = ""
    result = _check_ocr(settings)
    assert result.ok
    assert result.optional
    assert "ocr.base_url" in result.detail


def test_ocr_ok_when_vision_model_set(settings):
    settings.ocr.base_url = ""
    settings.ocr.vision_model = "llava:latest"
    result = _check_ocr(settings)
    assert result.ok
    assert result.optional
    assert "ocr.vision_model" in result.detail


def test_run_doctor_includes_ocr(settings):
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    row = next(item for item in run_doctor(settings, httpx_client=None) if item.name == "ocr")
    assert not row.ok
    assert row.optional
    assert "/v1/ocr" in row.detail
