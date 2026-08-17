"""E2E verification for OTel GenAI conventions (issue #167).

Boots a minimal OTLP/HTTP collector in-process, points daari's startup
bootstrap at it via OTEL_EXPORTER_OTLP_ENDPOINT, routes one request through
AppContext with a faked executor, and prints the gen_ai.* span attributes and
metric names the collector actually received over the wire.

Run: python scripts/smoke_otel_genai.py
Requires: pip install -e ".[dev]" (opentelemetry-sdk + otlp exporter).
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

received: dict[str, list[bytes]] = {"traces": [], "metrics": []}


class Collector(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        kind = "traces" if self.path.endswith("/v1/traces") else "metrics"
        received[kind].append(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()

    def log_message(self, *args):
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
    print(f"collector listening on {endpoint}")

    import tempfile

    from daari.config.settings import Settings
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
    from daari.router.router import AppContext

    tmp = tempfile.mkdtemp(prefix="daari-otel-smoke-")
    settings = Settings.model_validate(
        {
            "models": {"l3": "llama3.2:3b"},
            "observability": {"otel": True},
            "cache": {
                "l0": {"enabled": False, "path": f"{tmp}/l0"},
                "l1": {"enabled": False, "path": f"{tmp}/l1"},
            },
            "usage": {"path": f"{tmp}/ledger.sqlite3"},
            "trace": {"path": f"{tmp}/traces.sqlite3"},
            "learning": {
                "path": f"{tmp}/feedback.sqlite3",
                "examples_path": f"{tmp}/examples.sqlite3",
                "router_model_path": f"{tmp}/router-model.json",
            },
            "context": {"path": f"{tmp}/context"},
            "server": {"virtual_keys": {"path": f"{tmp}/virtual-keys.sqlite3"}},
            "enterprise": {"audit_path": f"{tmp}/audit.sqlite3"},
        }
    )
    ctx = AppContext.from_settings(settings)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="smoke answer",
            model="llama3.2:3b",
            finish_reason="stop",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                model="llama3.2:3b",
                latency_ms=42,
                input_tokens=17,
                output_tokens=5,
                usage_estimated=False,
            ),
        )

    for executor in (ctx.router.ollama, ctx.router.ollama_l4, ctx.router.ollama_l5):
        executor.execute = fake_execute

    response = asyncio.run(
        ctx.router.route(
            InternalRequest(
                messages=[Message(role="user", content="otel genai smoke")],
                model="llama3.2:3b",
                meta={"no_cache": True},
            )
        )
    )
    print(f"routed: tier={response.daari_meta.tier} model={response.model}")

    # Flush the batch/periodic exporters.
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace

    otel_trace.get_tracer_provider().force_flush()
    otel_metrics.get_meter_provider().force_flush()

    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
        ExportMetricsServiceRequest,
    )
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    ok = True
    span_names: list[str] = []
    genai_attrs: dict[str, object] = {}
    for payload in received["traces"]:
        req = ExportTraceServiceRequest()
        req.ParseFromString(payload)
        for rs in req.resource_spans:
            for ss in rs.scope_spans:
                for span in ss.spans:
                    span_names.append(span.name)
                    for attr in span.attributes:
                        if attr.key.startswith(("gen_ai.", "error.")):
                            value = attr.value
                            genai_attrs[attr.key] = (
                                value.int_value
                                if value.HasField("int_value")
                                else value.string_value or list(value.array_value.values)
                            )
    print(f"collector received spans: {span_names}")
    print("gen_ai attributes over the wire:")
    for key in sorted(genai_attrs):
        print(f"  {key} = {genai_attrs[key]!r}")
    if "chat llama3.2:3b" not in span_names:
        print("FAIL: no `chat llama3.2:3b` span reached the collector")
        ok = False
    if genai_attrs.get("gen_ai.usage.input_tokens") != 17:
        print("FAIL: gen_ai.usage.input_tokens missing or wrong")
        ok = False

    metric_names: set[str] = set()
    for payload in received["metrics"]:
        req = ExportMetricsServiceRequest()
        req.ParseFromString(payload)
        for rm in req.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    metric_names.add(metric.name)
    print(f"collector received metrics: {sorted(metric_names)}")
    for name in ("gen_ai.client.token.usage", "gen_ai.client.operation.duration"):
        if name not in metric_names:
            print(f"FAIL: metric {name} did not reach the collector")
            ok = False

    # Shut exporters down before the collector so the periodic metric reader
    # doesn't retry against a closed port.
    otel_metrics.get_meter_provider().shutdown()
    otel_trace.get_tracer_provider().shutdown()
    server.shutdown()
    print("SMOKE PASS" if ok else "SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
