"""OTLP logs export for gateway events (issue #849)."""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry._logs import set_logger_provider  # noqa: E402
from opentelemetry.sdk._logs import LoggerProvider  # noqa: E402
from opentelemetry.sdk._logs.export import (  # noqa: E402
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.trace import set_tracer_provider  # noqa: E402
from opentelemetry import trace as otel_trace  # noqa: E402

from daari.config.settings import Settings  # noqa: E402
from daari.gateway import request_log  # noqa: E402
from daari.gateway.request_log import configure_request_log, log_gateway_event  # noqa: E402
from daari.observability.otel import (  # noqa: E402
    configure_providers,
    export_gateway_log,
)


_EXPORTER = InMemoryLogRecordExporter()


@pytest.fixture(scope="module", autouse=True)
def _log_provider():
    provider = LoggerProvider(resource=Resource.create({"service.name": "daari-test"}))
    provider.add_log_record_processor(SimpleLogRecordProcessor(_EXPORTER))
    set_logger_provider(provider)
    set_tracer_provider(TracerProvider())
    yield


@pytest.fixture(autouse=True)
def _clear_and_restore(tmp_path):
    _EXPORTER.clear()
    configure_request_log(
        path=tmp_path / "requests.log",
        max_bytes=10_000,
        backups=1,
        structured_json_logs=False,
        otlp_logs=True,
    )
    yield
    configure_request_log(
        path=request_log.DEFAULT_LOG_PATH,
        max_bytes=request_log.DEFAULT_MAX_BYTES,
        backups=request_log.DEFAULT_BACKUPS,
        structured_json_logs=False,
        otlp_logs=False,
    )


def test_otlp_logs_default_off():
    assert Settings().observability.otlp_logs is False


def test_log_gateway_event_reaches_otlp_exporter():
    log_gateway_event("unit_otlp", {"request_id": "req-1", "tier": "L3"})

    finished = _EXPORTER.get_finished_logs()
    assert len(finished) == 1
    record = finished[0].log_record
    assert record.event_name == "unit_otlp"
    attrs = dict(record.attributes or {})
    assert attrs.get("daari.event") == "unit_otlp"
    assert attrs.get("request_id") == "req-1"
    assert attrs.get("tier") == "L3"


def test_export_gateway_log_correlates_with_active_span():
    tracer = otel_trace.get_tracer("daari-test")
    with tracer.start_as_current_span("parent") as span:
        assert export_gateway_log("correlated", {"k": "v"}) is True
        span_ctx = span.get_span_context()

    finished = _EXPORTER.get_finished_logs()
    assert len(finished) == 1
    record = finished[0].log_record
    assert record.trace_id == span_ctx.trace_id
    assert record.span_id == span_ctx.span_id


def test_export_gateway_log_fails_open_on_emit_error(monkeypatch):
    class _Boom:
        def emit(self, *args, **kwargs):
            raise RuntimeError("collector down")

    monkeypatch.setattr(
        "opentelemetry._logs.get_logger",
        lambda *a, **k: _Boom(),
    )
    assert export_gateway_log("x", {"a": 1}) is False


def test_configure_providers_otlp_logs_requires_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert configure_providers(otlp_logs=True) is False


def test_log_gateway_event_skips_otlp_when_disabled(tmp_path):
    configure_request_log(
        path=tmp_path / "requests.log",
        max_bytes=10_000,
        backups=1,
        otlp_logs=False,
    )
    log_gateway_event("no_otlp", {"x": 1})
    assert list(_EXPORTER.get_finished_logs()) == []
