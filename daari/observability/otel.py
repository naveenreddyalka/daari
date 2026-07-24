"""Optional OpenTelemetry export for RequestTrace steps (issue #115).

Off by default. When enabled and `opentelemetry-api` is installed, each
finished RequestTrace is exported as a span tree. Missing OTel packages are
a no-op so the core daemon never hard-depends on them.
"""

from __future__ import annotations

from typing import Any


def export_trace(trace: Any, *, service_name: str = "daari") -> bool:
    """Best-effort export. Returns True if a span was exported."""
    try:
        from opentelemetry import trace as otel_trace
    except ImportError:
        return False
    try:
        tracer = otel_trace.get_tracer(service_name)
        with tracer.start_as_current_span(f"daari.request.{getattr(trace, 'trace_id', '')}") as span:
            for step in getattr(trace, "steps", []) or []:
                name = step.get("step", "step")
                with tracer.start_as_current_span(name) as child:
                    detail = step.get("detail") or {}
                    for key, value in detail.items():
                        child.set_attribute(f"daari.{key}", str(value)[:200])
                    if "elapsed_ms" in step:
                        child.set_attribute("daari.elapsed_ms", int(step["elapsed_ms"]))
            span.set_attribute("daari.trace_id", getattr(trace, "trace_id", ""))
        return True
    except Exception:
        return False
