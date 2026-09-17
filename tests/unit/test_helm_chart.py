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