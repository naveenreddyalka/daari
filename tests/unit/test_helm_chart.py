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
            r"name: DAARI_OBSERVABILITY__BACKEND\s+value: postgres", rendered
        )
