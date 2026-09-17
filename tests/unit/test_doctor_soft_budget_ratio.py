"""Doctor soft_budget_ratio=0 with quotas/RPM (#530)."""

from __future__ import annotations

from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.setup.doctor import _check_soft_budget_ratio, run_doctor


class TestSoftBudgetRatioDoctor:
    def _down_client(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_warns_when_ratio_zero_and_rpm_set(self, settings):
        settings.frontier.soft_budget_ratio = 0.0
        settings.rate_limit.rpm = 60
        result = _check_soft_budget_ratio(settings)
        assert result.ok is False
        assert result.optional is True
        assert "soft_budget_ratio=0" in result.detail
        assert "rate_limit" in result.detail

    def test_warns_when_ratio_zero_and_request_quota_on_key(self, settings, tmp_path):
        settings.frontier.soft_budget_ratio = 0.0
        settings.rate_limit.rpm = 0
        settings.rate_limit.tpm = 0
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        store = VirtualKeyStore(settings.virtual_keys_path)
        store.create(
            "bot",
            client_id="bot",
            budget_windows=[BudgetWindow("day", 0.0, max_requests=100)],
        )
        result = _check_soft_budget_ratio(settings)
        assert result.ok is False
        assert "request-quota" in result.detail

    def test_warns_when_ratio_zero_and_usd_budget_on_key(self, settings, tmp_path):
        """USD-only windows also need soft bands (#637)."""
        settings.frontier.soft_budget_ratio = 0.0
        settings.rate_limit.rpm = 0
        settings.rate_limit.tpm = 0
        settings.rate_limit.model_rpm = 0
        settings.rate_limit.model_tpm = 0
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        store = VirtualKeyStore(settings.virtual_keys_path)
        store.create("bot", client_id="bot", daily_budget_usd=5.0)
        result = _check_soft_budget_ratio(settings)
        assert result.ok is False
        assert "USD budget" in result.detail

    def test_quiet_when_ratio_positive(self, settings):
        settings.frontier.soft_budget_ratio = 0.8
        settings.rate_limit.rpm = 60
        result = _check_soft_budget_ratio(settings)
        assert result.ok is True

    def test_quiet_when_ratio_zero_but_no_caps(self, settings, tmp_path):
        settings.frontier.soft_budget_ratio = 0.0
        settings.rate_limit.rpm = 0
        settings.rate_limit.tpm = 0
        settings.rate_limit.model_rpm = 0
        settings.rate_limit.model_tpm = 0
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        VirtualKeyStore(settings.virtual_keys_path).create("bot", client_id="bot")
        result = _check_soft_budget_ratio(settings)
        assert result.ok is True

    def test_run_doctor_includes_check(self, settings):
        settings.frontier.soft_budget_ratio = 0.0
        settings.rate_limit.tpm = 1000
        results = run_doctor(settings, httpx_client=self._down_client())
        by_name = {r.name: r for r in results}
        assert "soft_budget_ratio" in by_name
        assert by_name["soft_budget_ratio"].ok is False
