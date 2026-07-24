"""F3: optional OTel export (issue #115)."""

from __future__ import annotations

from daari.observability.otel import export_trace
from daari.observability.trace import RequestTrace


def test_export_trace_noop_without_otel():
    # Without opentelemetry installed this returns False; with it True.
    # Either way it must not raise.
    trace = RequestTrace()
    trace.add("cache_miss")
    result = export_trace(trace)
    assert isinstance(result, bool)
