"""Anthropic user-profile enforcement sync (#1866)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from daari.config.settings import AnthropicSettings, Settings
from daari.enterprise.enforcement_sync import (
    ENFORCED_STATUSES,
    EnforcementStore,
    end_users_for_profile,
    list_enforced_profiles,
    sync_enforcement,
)
from daari.observability.budget_alerts import verify_webhook_signature
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.setup.doctor import CheckResult, _check_anthropic_enforcement


def _profile(
    pid: str,
    status: str,
    *,
    actions: list[dict] | None = None,
) -> dict:
    return {
        "type": "user_profile",
        "id": pid,
        "enforcement_status": status,
        "enforcement_actions": actions
        or (
            [
                {
                    "type": "restriction",
                    "id": f"enac_{pid}",
                    "reason": "fraud_or_abuse",
                    "action": None,
                    "opened_at": "2026-10-02T19:30:00Z",
                    "expires_at": None,
                }
            ]
            if status in ENFORCED_STATUSES
            else []
        ),
    }


class TestListEnforcedProfiles:
    def test_filters_restricted_and_banned(self):
        pages = {
            None: {
                "data": [
                    _profile("uprof_a", "restricted"),
                    _profile("uprof_b", "banned"),
                ],
                "next_page": None,
            }
        }
        seen: dict[str, list[str]] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("x-api-key") == "sk-ant"
            assert request.headers.get("anthropic-version") == "2026-10-21"
            assert not (request.headers.get("anthropic-beta") or "").strip()
            statuses = request.url.params.get_list("enforcement_status[]")
            seen["statuses"] = statuses
            page = request.url.params.get("page")
            return httpx.Response(200, json=pages.get(page, {"data": [], "next_page": None}))

        transport = httpx.MockTransport(handler)
        rows = list_enforced_profiles(
            "sk-ant",
            base_url="https://api.anthropic.com",
            transport=transport,
        )
        assert {r["id"] for r in rows} == {"uprof_a", "uprof_b"}
        assert set(seen["statuses"]) == {"restricted", "banned"}

    def test_paginates(self):
        def handler(request: httpx.Request) -> httpx.Response:
            page = request.url.params.get("page")
            if page is None:
                return httpx.Response(
                    200,
                    json={
                        "data": [_profile("uprof_1", "restricted")],
                        "next_page": "cursor-2",
                    },
                )
            assert page == "cursor-2"
            return httpx.Response(
                200,
                json={"data": [_profile("uprof_2", "banned")], "next_page": None},
            )

        rows = list_enforced_profiles(
            "sk-ant",
            transport=httpx.MockTransport(handler),
        )
        assert [r["id"] for r in rows] == ["uprof_1", "uprof_2"]


class TestEnforcementStoreAndSync:
    def test_store_roundtrip(self, tmp_path: Path):
        store = EnforcementStore(tmp_path / "state.json")
        store.save(
            [
                {
                    "profile_id": "uprof_a",
                    "enforcement_status": "restricted",
                    "enforcement_actions": [],
                    "end_users": ["erin"],
                    "updated_at": "2026-10-22T00:00:00+00:00",
                }
            ]
        )
        loaded = store.load()
        assert loaded[0]["profile_id"] == "uprof_a"
        assert store.enforced_count() == 1

    def test_end_users_reverse_map(self):
        assert end_users_for_profile(
            "uprof_erin",
            {"erin": "uprof_erin", "k1": "uprof_erin", "other": "uprof_x"},
        ) == ["erin", "k1"]

    def test_sync_emits_started_and_ended_events(self, tmp_path: Path, monkeypatch):
        events: list[tuple[str, dict]] = []

        def _log(name: str, payload: dict | None = None, **_kwargs) -> None:
            events.append((name, payload or {}))

        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            _log,
        )

        state = tmp_path / "enf.json"
        store = EnforcementStore(state)
        store.save(
            [
                {
                    "profile_id": "uprof_old",
                    "enforcement_status": "restricted",
                    "enforcement_actions": [],
                    "end_users": ["bob"],
                    "updated_at": "2026-10-21T00:00:00+00:00",
                }
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [_profile("uprof_new", "banned")],
                    "next_page": None,
                },
            )

        result = sync_enforcement(
            api_key="sk-ant",
            user_profiles={"erin": "uprof_new", "bob": "uprof_old"},
            store=store,
            transport=httpx.MockTransport(handler),
        )
        assert result.enforced_count == 1
        assert {r["profile_id"] for r in store.load()} == {"uprof_new"}
        names = [n for n, _ in events]
        assert "anthropic.enforcement_started" in names
        assert "anthropic.enforcement_ended" in names
        started = next(p for n, p in events if n == "anthropic.enforcement_started")
        assert started["profile_id"] == "uprof_new"
        assert started["enforcement_status"] == "banned"
        assert "erin" in started["end_users"]
        ended = next(p for n, p in events if n == "anthropic.enforcement_ended")
        assert ended["profile_id"] == "uprof_old"

    def test_sync_posts_signed_webhook(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            lambda *_a, **_k: None,
        )
        posted: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if "user_profiles" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "data": [_profile("uprof_a", "restricted")],
                        "next_page": None,
                    },
                )
            posted.append(request)
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        sync_enforcement(
            api_key="sk-ant",
            user_profiles={"erin": "uprof_a"},
            store=EnforcementStore(tmp_path / "s.json"),
            transport=transport,
            webhook_url="https://hooks.example/enforcement",
            webhook_secret="whsec",
        )
        assert len(posted) == 1
        req = posted[0]
        body = req.content
        ts = req.headers["X-Daari-Timestamp"]
        sig = req.headers["X-Daari-Signature"]
        assert verify_webhook_signature(body, sig, "whsec", ts)
        payload = json.loads(body)
        assert payload["event"] == "anthropic.enforcement"
        assert payload["started"][0]["profile_id"] == "uprof_a"


class TestPrometheusAndDoctor:
    def test_prometheus_gauge(self):
        text = render_prometheus(Metrics(), anthropic_enforced_profiles=2)
        assert "# TYPE daari_anthropic_enforced_profiles gauge" in text
        assert "daari_anthropic_enforced_profiles 2" in text

    def test_doctor_tips_when_mapped_enforced(self, tmp_path: Path):
        store = EnforcementStore(tmp_path / "e.json")
        store.save(
            [
                {
                    "profile_id": "uprof_x",
                    "enforcement_status": "restricted",
                    "enforcement_actions": [],
                    "end_users": ["erin"],
                    "updated_at": "2026-10-22T00:00:00+00:00",
                }
            ]
        )
        settings = Settings(
            anthropic=AnthropicSettings(
                user_profiles={"erin": "uprof_x"},
                enforcement_state_path=str(tmp_path / "e.json"),
            )
        )
        tip = _check_anthropic_enforcement(settings)
        assert isinstance(tip, CheckResult)
        assert tip.ok is False
        assert tip.name == "anthropic_enforcement"
        assert "uprof_x" in tip.detail or "restricted" in tip.detail

    def test_doctor_ok_when_clear(self, tmp_path: Path):
        settings = Settings(
            anthropic=AnthropicSettings(
                user_profiles={"erin": "uprof_x"},
                enforcement_state_path=str(tmp_path / "missing.json"),
            )
        )
        tip = _check_anthropic_enforcement(settings)
        assert tip.ok is True
