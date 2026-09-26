"""Per-modality Prometheus/OTel metrics (#1106)."""

from __future__ import annotations

from daari.observability.metrics import Metrics, genai_operation_name, infer_modality
from daari.observability.prometheus import render_prometheus


def test_infer_modality_from_tier():
    assert infer_modality("L3") == "chat"
    assert infer_modality("embed") == "embed"
    assert infer_modality("tts") == "tts"
    assert infer_modality("asr") == "asr"
    assert infer_modality("asr-local") == "asr"
    assert infer_modality("images") == "images"
    assert infer_modality("moderations") == "moderations"
    assert infer_modality("rerank") == "rerank"


def test_genai_operation_names():
    assert genai_operation_name("chat") == "chat"
    assert genai_operation_name("embed") == "embeddings"
    assert genai_operation_name("tts") == "text_to_speech"
    assert genai_operation_name("asr") == "transcription"
    assert genai_operation_name("images") == "image_generation"
    assert genai_operation_name("moderations") == "moderation"
    assert genai_operation_name("rerank") == "rerank"


def test_tokens_and_modality_request_series():
    metrics = Metrics()
    metrics.record("L3", modality="chat", input_tokens=10, output_tokens=5, latency_ms=1)
    metrics.record("images", modality="images", input_tokens=2, latency_ms=1)
    metrics.record("moderations", modality="moderations", input_tokens=8, latency_ms=1)
    metrics.record("rerank", modality="rerank", input_tokens=3, latency_ms=1)
    text = render_prometheus(metrics)
    assert 'daari_requests_total{tier="L3"} 1' in text
    assert 'daari_requests_total{tier="L3",modality="chat"} 1' in text
    assert 'daari_requests_total{tier="images",modality="images"} 1' in text
    assert 'daari_tokens_total{modality="chat",tier="L3",direction="input"} 10' in text
    assert 'daari_tokens_total{modality="chat",tier="L3",direction="output"} 5' in text
    assert 'daari_tokens_total{modality="images",tier="images",direction="input"} 2' in text
    assert 'daari_tokens_total{modality="moderations",tier="moderations",direction="input"} 8' in text
    assert 'daari_tokens_total{modality="rerank",tier="rerank",direction="input"} 3' in text


def test_images_moderations_rerank_record_helpers_hit_metrics():
    from daari.gateway import images, moderations, rerank

    class Ctx:
        def __init__(self):
            self.metrics = Metrics()
            self.router = type("R", (), {"usage_ledger": None})()

    ctx = Ctx()
    images._record_request(ctx, client_id="c", model="dall-e-3", prompt="hi", n=2)
    moderations._record_request(ctx, client_id="c", model="omni", input_text="abcd")
    rerank._record_request(
        ctx, client_id="c", model="rerank-v1", query="q", documents=["a", "b"]
    )
    text = render_prometheus(ctx.metrics)
    assert 'modality="images"' in text
    assert 'modality="moderations"' in text
    assert 'modality="rerank"' in text
    assert "daari_tokens_total" in text


def test_grafana_dashboard_has_modality_panels():
    import json
    from pathlib import Path

    raw = Path("deploy/grafana/daari-dashboard.json").read_text()
    dash = json.loads(raw)
    titles = {p["title"] for p in dash["panels"]}
    assert "Tokens by modality" in titles
    assert "Requests by modality" in titles
    assert "daari_tokens_total" in raw
