"""capacity-helm documents TTS, frontier fallback, and OTLP log knobs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/guides/operations/capacity-helm.md"


def test_capacity_helm_documents_tts_base_url() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "tts.baseUrl" in text
    assert "DAARI_TTS__BASE_URL" in text


def test_capacity_helm_documents_tts_model_and_voice() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "tts.model" in text
    assert "tts.voice" in text
    assert "DAARI_TTS__MODEL" in text
    assert "DAARI_TTS__VOICE" in text


def test_capacity_helm_documents_asr_model() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "asr.model" in text
    assert "DAARI_ASR__MODEL" in text


def test_capacity_helm_documents_local_pool_frontier_fallback() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "localPool.frontierFallback" in text
    assert "DAARI_ROUTING__LOCAL_POOL__FRONTIER_FALLBACK" in text


def test_capacity_helm_documents_asr_frontier_fallback() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "asr.frontierFallback" in text
    assert "DAARI_ASR__FRONTIER_FALLBACK" in text


def test_capacity_helm_documents_otlp_logs() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "otlpLogs" in text or "observability.otlpLogs" in text
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in text
    assert "DAARI_OBSERVABILITY__OTLP_LOGS" in text


def test_capacity_helm_documents_session_affinity_and_policy_sync() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "routing.sessionAffinity" in text
    assert "DAARI_ROUTING__SESSION_AFFINITY" in text
    assert "enterprise.policySync" in text
    assert "DAARI_ENTERPRISE__POLICY_SYNC_URL" in text
    assert "DAARI_ENTERPRISE__CONFIG_SIGNING_SECRET" in text


def test_capacity_helm_documents_header_policy() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "server.headerPolicy" in text
    assert "DAARI_SERVER__HEADER_POLICY__ENABLED" in text
    assert "header_policy" in text
