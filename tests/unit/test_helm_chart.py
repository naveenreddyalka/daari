"""Helm chart stays aligned with the packaged release (#476)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from daari import __version__

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "daari"
VALUES = CHART / "values.yaml"
CHART_YAML = CHART / "Chart.yaml"
NOTES = CHART / "templates" / "NOTES.txt"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _helm_template(*set_args: str) -> str:
    cmd = ["helm", "template", "daari", str(CHART), *set_args]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


@pytest.fixture(scope="module")
def helm_available() -> None:
    try:
        subprocess.run(["helm", "version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"helm not available: {exc}")


class TestHelmChartReleasePin:
    def test_image_tag_and_app_version_match_package(self) -> None:
        chart = _load_yaml(CHART_YAML)
        values = _load_yaml(VALUES)
        assert chart["appVersion"] == __version__
        assert str(values["image"]["tag"]) == __version__

    def test_values_comment_warns_about_sqlite_split_brain(self) -> None:
        text = VALUES.read_text(encoding="utf-8")
        assert re.search(r"per-pod|split", text, re.I)
        assert "postgres.enabled" in text
        assert "batches" in text.lower() or "SQLite" in text

    def test_notes_txt_documents_multi_replica_sqlite_warning(self) -> None:
        text = NOTES.read_text(encoding="utf-8")
        assert "daari.fleetSqliteWarning" in text
        assert "per-pod SQLite" in text
        assert "DAARI_BATCHES__BACKEND" in text

    def test_notes_txt_documents_servicemonitor_and_org_pool(self) -> None:
        text = NOTES.read_text(encoding="utf-8")
        assert ".Values.serviceMonitor.enabled" in text
        assert "/metrics" in text
        assert "bearerTokenSecret" in text
        assert ".Values.orgPool.enabled" in text
        assert ".Values.orgPool.baseUrl" in text
        assert "DAARI_ROUTING__ORG_POOL" in text


def _helm_notes(*set_args: str) -> str:
    """Render NOTES.txt (helm template skips NOTES; wrap via tpl + ConfigMap)."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "daari"
        shutil.copytree(CHART, dest)
        notes_src = dest / "templates" / "NOTES.txt"
        notes_body = notes_src.read_text(encoding="utf-8")
        notes_src.unlink()
        (dest / "notes-body.txt").write_text(notes_body, encoding="utf-8")
        (dest / "templates" / "notes-render.yaml").write_text(
            "\n".join(
                [
                    "apiVersion: v1",
                    "kind: ConfigMap",
                    "metadata:",
                    "  name: daari-notes-render",
                    "data:",
                    "  notes: |",
                    '{{ tpl (.Files.Get "notes-body.txt") . | indent 4 }}',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        cmd = ["helm", "template", "daari", str(dest), *set_args]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        block = result.stdout.split("name: daari-notes-render")[-1]
        lines: list[str] = []
        in_notes = False
        for line in block.splitlines():
            if line.startswith("  notes:"):
                in_notes = True
                continue
            if in_notes:
                if line.startswith("    "):
                    lines.append(line[4:])
                elif line.strip() == "":
                    lines.append("")
                else:
                    break
        return "\n".join(lines)


class TestHelmNotesAndFleetEnv:
    def test_annotation_warns_when_multi_replica_without_postgres(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template(
            "--set",
            "replicaCount=2",
            "--set",
            "autoscaling.enabled=false",
            "--set",
            "postgres.enabled=false",
        )
        assert "daari.dev/fleet-sqlite-warning" in rendered
        assert "per-pod SQLite" in rendered

    def test_annotation_warns_when_hpa_min_without_postgres(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template(
            "--set",
            "replicaCount=1",
            "--set",
            "autoscaling.enabled=true",
            "--set",
            "autoscaling.minReplicas=2",
            "--set",
            "postgres.enabled=false",
        )
        assert "daari.dev/fleet-sqlite-warning" in rendered

    def test_annotation_absent_when_postgres_enabled(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "replicaCount=2",
            "--set",
            "postgres.enabled=true",
            "--set",
            "postgres.url=postgresql://daari:daari@postgres:5432/daari",
        )
        assert "daari.dev/fleet-sqlite-warning" not in rendered

    def test_defaults_are_single_replica(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "daari.dev/fleet-sqlite-warning" not in rendered
        assert re.search(r"name: DAARI_FLEET_REPLICAS\s+value: \"1\"", rendered)

    def test_deployment_sets_fleet_replicas_and_postgres_backends(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template(
            "--set",
            "replicaCount=2",
            "--set",
            "autoscaling.enabled=false",
            "--set",
            "postgres.enabled=true",
            "--set",
            "postgres.url=postgresql://daari:daari@postgres:5432/daari",
        )
        assert "DAARI_FLEET_REPLICAS" in rendered
        assert re.search(r"name: DAARI_BATCHES__BACKEND\s+value: postgres", rendered)
        assert re.search(r"name: DAARI_FILES__BACKEND\s+value: postgres", rendered)
        assert re.search(r"name: DAARI_RESPONSES__BACKEND\s+value: postgres", rendered)
        assert re.search(
            r"name: DAARI_ENTERPRISE__AUDIT_BACKEND\s+value: postgres", rendered
        )
        assert re.search(
            r"name: DAARI_SERVER__VIRTUAL_KEYS__BACKEND\s+value: postgres", rendered
        )
        assert re.search(
            r"name: DAARI_OBSERVABILITY__BACKEND\s+value: postgres", rendered
        )


class TestHelmGracefulRollout:
    def test_defaults_render_grace_prestop_and_strategy(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "terminationGracePeriodSeconds: 60" in rendered
        assert "preStop:" in rendered
        assert "sleep 5" in rendered
        assert "maxUnavailable: 0" in rendered
        assert "maxSurge: 1" in rendered
        values = _load_yaml(VALUES)
        assert values["terminationGracePeriodSeconds"] == 60
        assert values["lifecycle"]["preStopSleepSeconds"] == 5
        assert values["strategy"]["rollingUpdate"]["maxUnavailable"] == 0

    def test_prestop_omitted_when_sleep_zero(self, helm_available: None) -> None:
        rendered = _helm_template("--set", "lifecycle.preStopSleepSeconds=0")
        assert "preStop:" not in rendered
        assert "terminationGracePeriodSeconds: 60" in rendered


class TestHelmSecurityAndPdb:
    def test_defaults_render_security_contexts_and_writable_mounts(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template()
        assert "runAsNonRoot: true" in rendered
        assert "runAsUser: 1000" in rendered
        assert "readOnlyRootFilesystem: true" in rendered
        assert "allowPrivilegeEscalation: false" in rendered
        assert "drop:" in rendered
        assert "ALL" in rendered
        assert "mountPath: /home/daari/.daari" in rendered
        assert "mountPath: /tmp" in rendered
        assert "kind: PodDisruptionBudget" not in rendered
        values = _load_yaml(VALUES)
        assert values["podSecurityContext"]["runAsNonRoot"] is True
        assert values["securityContext"]["readOnlyRootFilesystem"] is True
        assert values["podDisruptionBudget"]["enabled"] is False

    def test_pdb_renders_when_enabled(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "podDisruptionBudget.enabled=true",
            "--set",
            "podDisruptionBudget.minAvailable=2",
        )
        assert "kind: PodDisruptionBudget" in rendered
        assert "minAvailable: 2" in rendered

    def test_pdb_prefers_max_unavailable_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "podDisruptionBudget.enabled=true",
            "--set",
            "podDisruptionBudget.maxUnavailable=1",
        )
        assert "kind: PodDisruptionBudget" in rendered
        assert "maxUnavailable: 1" in rendered
        assert "minAvailable:" not in rendered.split("kind: PodDisruptionBudget")[1]


class TestHelmServiceMonitor:
    def test_servicemonitor_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "kind: ServiceMonitor" not in rendered
        values = _load_yaml(VALUES)
        assert values["serviceMonitor"]["enabled"] is False

    def test_servicemonitor_scrapes_metrics_when_enabled(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template("--set", "serviceMonitor.enabled=true")
        assert "kind: ServiceMonitor" in rendered
        assert "apiVersion: monitoring.coreos.com/v1" in rendered
        sm = rendered.split("kind: ServiceMonitor")[1]
        assert "path: /metrics" in sm
        assert "port: http" in sm
        assert "app.kubernetes.io/name: daari" in sm
        assert "bearerTokenSecret" not in sm
        assert "authorization:" not in sm
        values = _load_yaml(VALUES)
        assert values["serviceMonitor"].get("bearerTokenSecret") in (None, {})

    def test_servicemonitor_bearer_token_secret_when_set(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template(
            "--set",
            "serviceMonitor.enabled=true",
            "--set",
            "serviceMonitor.bearerTokenSecret.name=daari-metrics-token",
            "--set",
            "serviceMonitor.bearerTokenSecret.key=token",
        )
        sm = rendered.split("kind: ServiceMonitor")[1]
        assert "path: /metrics" in sm
        assert re.search(
            r"authorization:\s+type:\s+Bearer\s+credentials:\s+"
            r"name:\s+daari-metrics-token\s+key:\s+token",
            sm,
        ) or (
            "bearerTokenSecret:" in sm
            and "name: daari-metrics-token" in sm
            and "key: token" in sm
        )

    def test_servicemonitor_targets_metrics_port_when_set(
        self, helm_available: None
    ) -> None:
        """Private scrape listener needs no bearer (#602)."""
        rendered = _helm_template(
            "--set",
            "serviceMonitor.enabled=true",
            "--set",
            "observability.metricsPort=9090",
            "--set",
            "serviceMonitor.bearerTokenSecret.name=daari-metrics-token",
            "--set",
            "serviceMonitor.bearerTokenSecret.key=token",
        )
        sm = rendered.split("kind: ServiceMonitor")[1]
        assert "port: metrics" in sm
        assert "path: /metrics" in sm
        assert "authorization:" not in sm
        assert "bearerTokenSecret:" not in sm


class TestHelmMetricsPort:
    def test_metrics_port_off_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_OBSERVABILITY__METRICS_PORT" not in rendered
        assert "name: metrics" not in rendered
        values = _load_yaml(VALUES)
        assert int(values.get("observability", {}).get("metricsPort") or 0) == 0

    def test_metrics_port_wires_env_container_and_service(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template("--set", "observability.metricsPort=9090")
        assert re.search(
            r'name: DAARI_OBSERVABILITY__METRICS_PORT\s+value: "9090"', rendered
        )
        assert re.search(
            r"name: metrics\s+containerPort: 9090", rendered
        ) or ("containerPort: 9090" in rendered and "name: metrics" in rendered)
        svc = rendered.split("kind: Service")[1].split("---")[0]
        assert "name: metrics" in svc
        assert "port: 9090" in svc
        assert "targetPort: metrics" in svc


class TestHelmOtlpLogs:
    def test_otlp_logs_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_OBSERVABILITY__OTLP_LOGS" not in rendered
        assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in rendered
        values = _load_yaml(VALUES)
        obs = values["observability"]
        assert obs["otlpLogs"] is False
        assert obs["otlpEndpoint"] == ""

    def test_otlp_logs_and_endpoint_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "observability.otlpLogs=true",
            "--set",
            "observability.otlpEndpoint=http://otel-collector:4318",
        )
        assert re.search(
            r'name: DAARI_OBSERVABILITY__OTLP_LOGS\s+value: "true"',
            rendered,
        )
        assert re.search(
            r'name: OTEL_EXPORTER_OTLP_ENDPOINT\s+value: "http://otel-collector:4318"',
            rendered,
        )


class TestHelmOrgPool:
    def test_org_pool_env_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_ROUTING__ORG_POOL__ENABLED" not in rendered
        assert "DAARI_ROUTING__ORG_POOL__BASE_URL" not in rendered
        values = _load_yaml(VALUES)
        assert values["orgPool"]["enabled"] is False

    def test_org_pool_env_when_enabled(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "orgPool.enabled=true",
            "--set",
            "orgPool.baseUrl=http://gpu-pool:11434",
        )
        assert re.search(
            r'name: DAARI_ROUTING__ORG_POOL__ENABLED\s+value: "true"', rendered
        )
        assert re.search(
            r'name: DAARI_ROUTING__ORG_POOL__BASE_URL\s+value: "http://gpu-pool:11434"',
            rendered,
        )


class TestHelmOllamaBaseUrl:
    def test_ollama_base_url_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_OLLAMA__BASE_URL" not in rendered
        values = _load_yaml(VALUES)
        assert values["ollama"]["baseUrl"] == ""

    def test_ollama_base_url_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "ollama.baseUrl=http://ollama.internal:11434",
        )
        assert re.search(
            r'name: DAARI_OLLAMA__BASE_URL\s+value: "http://ollama.internal:11434"',
            rendered,
        )


class TestHelmAsrBaseUrl:
    def test_asr_base_url_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_ASR__BASE_URL" not in rendered
        values = _load_yaml(VALUES)
        assert values["asr"]["baseUrl"] == ""

    def test_asr_base_url_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "asr.baseUrl=http://whisper.internal:8000/v1",
        )
        assert re.search(
            r'name: DAARI_ASR__BASE_URL\s+value: "http://whisper.internal:8000/v1"',
            rendered,
        )


class TestHelmAsrFrontierFallback:
    def test_asr_frontier_fallback_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_ASR__FRONTIER_FALLBACK" not in rendered
        values = _load_yaml(VALUES)
        assert values["asr"]["frontierFallback"] is False

    def test_asr_frontier_fallback_when_enabled(self, helm_available: None) -> None:
        rendered = _helm_template("--set", "asr.frontierFallback=true")
        assert re.search(
            r'name: DAARI_ASR__FRONTIER_FALLBACK\s+value: "true"',
            rendered,
        )


class TestHelmTtsBaseUrl:
    def test_tts_base_url_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_TTS__BASE_URL" not in rendered
        values = _load_yaml(VALUES)
        assert values["tts"]["baseUrl"] == ""

    def test_tts_base_url_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "tts.baseUrl=http://kokoro.internal:8880/v1",
        )
        assert re.search(
            r'name: DAARI_TTS__BASE_URL\s+value: "http://kokoro.internal:8880/v1"',
            rendered,
        )


class TestHelmTtsModelVoice:
    def test_tts_model_voice_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_TTS__MODEL" not in rendered
        assert "DAARI_TTS__VOICE" not in rendered
        values = _load_yaml(VALUES)
        assert values["tts"]["model"] == ""
        assert values["tts"]["voice"] == ""

    def test_tts_model_voice_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "tts.model=kokoro",
            "--set",
            "tts.voice=af_bella",
        )
        assert re.search(r'name: DAARI_TTS__MODEL\s+value: "kokoro"', rendered)
        assert re.search(r'name: DAARI_TTS__VOICE\s+value: "af_bella"', rendered)


class TestHelmAsrModel:
    def test_asr_model_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_ASR__MODEL" not in rendered
        values = _load_yaml(VALUES)
        assert values["asr"]["model"] == ""

    def test_asr_model_when_set(self, helm_available: None) -> None:
        rendered = _helm_template("--set", "asr.model=ggml-base")
        assert re.search(r'name: DAARI_ASR__MODEL\s+value: "ggml-base"', rendered)


class TestHelmRequestDeadlineAndRetention:
    def test_deadline_and_request_log_absent_by_default(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template()
        assert "DAARI_UPSTREAM__REQUEST_DEADLINE_SECONDS" not in rendered
        assert "DAARI_OBSERVABILITY__RETENTION__REQUEST_LOG_DAYS" not in rendered
        values = _load_yaml(VALUES)
        assert values["upstream"]["requestDeadlineSeconds"] in ("", None)
        assert values["observability"]["retention"]["requestLogDays"] in ("", None)

    def test_deadline_and_request_log_when_set(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "upstream.requestDeadlineSeconds=120",
            "--set",
            "observability.retention.requestLogDays=30",
        )
        assert re.search(
            r'name: DAARI_UPSTREAM__REQUEST_DEADLINE_SECONDS\s+value: "120"',
            rendered,
        )
        assert re.search(
            r'name: DAARI_OBSERVABILITY__RETENTION__REQUEST_LOG_DAYS\s+value: "30"',
            rendered,
        )


class TestHelmNotesServiceMonitorAndOrgPool:
    def test_notes_omit_servicemonitor_and_org_pool_by_default(
        self, helm_available: None
    ) -> None:
        notes = _helm_notes()
        assert "ServiceMonitor enabled" not in notes
        assert "Org pool enabled" not in notes

    def test_notes_servicemonitor_scrape_and_bearer_hint(
        self, helm_available: None
    ) -> None:
        notes = _helm_notes("--set", "serviceMonitor.enabled=true")
        assert "ServiceMonitor enabled" in notes
        assert "/metrics" in notes
        assert "bearerTokenSecret" in notes
        assert "Bearer" in notes

    def test_notes_org_pool_echoes_base_url(self, helm_available: None) -> None:
        notes = _helm_notes(
            "--set",
            "orgPool.enabled=true",
            "--set",
            "orgPool.baseUrl=http://gpu-pool:11434",
        )
        assert "Org pool enabled" in notes
        assert "DAARI_ROUTING__ORG_POOL__ENABLED" in notes
        assert "http://gpu-pool:11434" in notes


class TestHelmKedaRequestRate:
    def test_scaledobject_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "kind: ScaledObject" not in rendered
        assert "keda.sh" not in rendered
        values = _load_yaml(VALUES)
        assert values["autoscaling"]["keda"]["enabled"] is False
        assert "kind: HorizontalPodAutoscaler" in rendered

    def test_enabled_render_has_query_threshold_and_cpu_hpa(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template("--set", "autoscaling.keda.enabled=true")
        assert "kind: ScaledObject" in rendered
        assert "apiVersion: keda.sh/v1alpha1" in rendered
        assert "sum(rate(daari_requests_total[1m]))" in rendered
        assert 'threshold: "50"' in rendered
        assert "kind: HorizontalPodAutoscaler" in rendered
        assert "averageUtilization: 70" in rendered
        assert "minReplicaCount: 1" in rendered

    def test_keda_min_above_one_without_postgres_is_refused(
        self, helm_available: None
    ) -> None:
        with pytest.raises(subprocess.CalledProcessError) as exc:
            _helm_template(
                "--set",
                "autoscaling.keda.enabled=true",
                "--set",
                "autoscaling.keda.minReplicaCount=2",
                "--set",
                "postgres.enabled=false",
            )
        assert "postgres.enabled" in exc.value.stderr
        assert "minReplicaCount" in exc.value.stderr

    def test_keda_min_above_one_allowed_with_postgres(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "autoscaling.keda.enabled=true",
            "--set",
            "autoscaling.keda.minReplicaCount=2",
            "--set",
            "postgres.enabled=true",
        )
        assert "minReplicaCount: 2" in rendered
        assert "kind: HorizontalPodAutoscaler" in rendered



class TestHelmLocalPoolFrontierFallback:
    def test_frontier_fallback_absent_by_default(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_ROUTING__LOCAL_POOL__FRONTIER_FALLBACK" not in rendered
        values = _load_yaml(VALUES)
        assert values["localPool"]["frontierFallback"] is False

    def test_frontier_fallback_when_enabled(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "localPool.frontierFallback=true",
        )
        assert re.search(
            r'name: DAARI_ROUTING__LOCAL_POOL__FRONTIER_FALLBACK\s+value: "true"',
            rendered,
        )


class TestHelmAuthRateLimitFrontier:
    def test_defaults_omit_auth_rate_frontier_env(self, helm_available: None) -> None:
        rendered = _helm_template()
        assert "DAARI_SERVER__API_KEY" not in rendered
        assert "DAARI_RATE_LIMIT__RPM" not in rendered
        assert "DAARI_FRONTIER__ENABLED" not in rendered
        assert "DAARI_FRONTIER_API_KEY" not in rendered
        values = _load_yaml(VALUES)
        assert values["server"]["apiKeySecret"] == {}
        assert values["rateLimit"]["enabled"] is False
        assert values["frontier"]["enabled"] is False

    def test_secrets_and_rate_limit_env_render(self, helm_available: None) -> None:
        rendered = _helm_template(
            "--set",
            "server.apiKeySecret.name=daari-master",
            "--set",
            "server.apiKeySecret.key=api-key",
            "--set",
            "rateLimit.enabled=true",
            "--set",
            "rateLimit.rpm=120",
            "--set",
            "rateLimit.tpm=50000",
            "--set",
            "rateLimit.redisUrl=redis://rl:6379/1",
            "--set",
            "frontier.enabled=true",
            "--set",
            "frontier.apiKeySecret.name=daari-frontier",
            "--set",
            "frontier.apiKeySecret.key=token",
        )
        assert "DAARI_SERVER__API_KEY" in rendered
        assert 'name: "daari-master"' in rendered
        assert 'key: "api-key"' in rendered
        assert re.search(r"name: DAARI_RATE_LIMIT__RPM\s+value: \"120\"", rendered)
        assert re.search(r"name: DAARI_RATE_LIMIT__TPM\s+value: \"50000\"", rendered)
        assert re.search(r"name: DAARI_CACHE__BACKEND\s+value: redis", rendered)
        assert "redis://rl:6379/1" in rendered
        assert re.search(r"name: DAARI_FRONTIER__ENABLED\s+value: \"true\"", rendered)
        assert "DAARI_FRONTIER_API_KEY" in rendered
        assert 'name: "daari-frontier"' in rendered
        assert 'key: "token"' in rendered

    def test_rate_limit_reuses_cache_redis_without_duplicate_url(
        self, helm_available: None
    ) -> None:
        rendered = _helm_template(
            "--set",
            "redis.enabled=true",
            "--set",
            "redis.url=redis://shared:6379/0",
            "--set",
            "rateLimit.enabled=true",
            "--set",
            "rateLimit.rpm=60",
            "--set",
            "rateLimit.redisUrl=redis://should-not-appear:6379/9",
        )
        assert rendered.count("DAARI_CACHE__REDIS_URL") == 1
        assert "redis://shared:6379/0" in rendered
        assert "redis://should-not-appear" not in rendered

    def test_notes_document_auth_rate_frontier(self, helm_available: None) -> None:
        text = NOTES.read_text(encoding="utf-8")
        assert "server.apiKeySecret" in text or "DAARI_SERVER__API_KEY" in text
        assert "rateLimit" in text
        assert "frontier" in text
        notes = _helm_notes(
            "--set",
            "server.apiKeySecret.name=daari-master",
            "--set",
            "rateLimit.enabled=true",
            "--set",
            "rateLimit.rpm=10",
            "--set",
            "frontier.enabled=true",
            "--set",
            "frontier.apiKeySecret.name=daari-frontier",
        )
        assert "Master API key" in notes
        assert "Rate limits enabled" in notes
        assert "per-pod SQLite" in notes
        assert "Frontier enabled" in notes
        assert "DAARI_FRONTIER_API_KEY" in notes
