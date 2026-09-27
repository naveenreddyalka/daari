"""Doctor dry-checks OpenAPI for Responses stream resume (#1161)."""

from __future__ import annotations

from daari.setup.doctor import _check_responses_stream_resume, run_doctor
from daari.server.app import create_app


def test_openapi_get_response_documents_stream_resume(settings):
    op = create_app(settings).openapi()["paths"]["/v1/responses/{response_id}"]["get"]
    by_name = {p["name"]: p for p in op.get("parameters", [])}
    assert by_name["stream"].get("description")
    assert by_name["starting_after"].get("description")
    assert "409" in op.get("responses", {})


def test_doctor_responses_stream_resume_ok(settings):
    result = _check_responses_stream_resume(settings)
    assert result.name == "responses_stream_resume"
    assert result.ok
    assert result.optional
    assert "stream" in result.detail
    assert "starting_after" in result.detail
    assert "409" in result.detail


def test_doctor_responses_stream_resume_missing_warns(settings):
    result = _check_responses_stream_resume(
        settings,
        openapi_paths={"/v1/responses/{response_id}": {"get": {"parameters": [], "responses": {}}}},
    )
    assert not result.ok
    assert result.optional
    assert "starting_after" in result.detail or "stream" in result.detail


def test_run_doctor_includes_responses_stream_resume(settings):
    row = next(
        item
        for item in run_doctor(settings, httpx_client=None)
        if item.name == "responses_stream_resume"
    )
    assert row.ok
    assert "409" in row.detail
