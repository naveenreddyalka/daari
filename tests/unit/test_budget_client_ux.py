"""Train 5 budget & client UX: soft budgets, attribution, PII scrub (issue #74)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.gateway.pii import scrub_messages, scrub_pii
from daari.observability.metrics import Metrics
from daari.observability.usage import UsageLedger
from daari.router.router import OllamaExecutor, Router


class TestPiiScrub:
    def test_email_phone_ssn_card_ip(self):
        text = (
            "Mail bob@example.com or call 415-555-1234. SSN 123-45-6789, "
            "card 4111 1111 1111 1111, server 192.168.0.10."
        )
        scrubbed, counts = scrub_pii(text)
        assert "bob@example.com" not in scrubbed
        assert "<email-1>" in scrubbed
        assert "415-555-1234" not in scrubbed
        assert "123-45-6789" not in scrubbed
        assert "4111 1111 1111 1111" not in scrubbed
        assert "192.168.0.10" not in scrubbed
        assert counts == {"email": 1, "phone": 1, "ssn": 1, "card": 1, "ip": 1}

    def test_same_value_gets_same_placeholder(self):
        scrubbed, counts = scrub_pii("a@b.co wrote to a@b.co and c@d.co")
        assert scrubbed.count("<email-1>") == 2
        assert "<email-2>" in scrubbed
        assert counts == {"email": 3}

    def test_clean_text_untouched(self):
        text = "Refactor the parser module to use iterators."
        scrubbed, counts = scrub_pii(text)
        assert scrubbed == text
        assert counts == {}

    def test_scrub_messages_skips_system(self):
        messages = [
            Message(role="system", content="Contact ops@daari.dev for policy."),
            Message(role="user", content="email me at bob@example.com"),
        ]
        scrubbed, counts = scrub_messages(messages)
        assert scrubbed[0].content == "Contact ops@daari.dev for policy."
        assert "<email-1>" in scrubbed[1].content
        assert counts == {"email": 1}


class TestLedgerClientAttribution:
    def test_by_client_grouping(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        ledger.record(tier="L3", prompt_chars=400, completion_chars=400, client_id="cursor")
        ledger.record(tier="L3", prompt_chars=100, completion_chars=100, client_id="cursor")
        ledger.record(tier="L6", prompt_chars=200, completion_chars=200, client_id="cli")
        ledger.record(tier="L0", cache_hit=True, client_id=None)

        clients = ledger.by_client(days=7, frontier_price_per_1k_tokens=0.002)
        by_id = {entry["client_id"]: entry for entry in clients}
        assert by_id["cursor"]["requests"] == 2
        assert by_id["cursor"]["frontier_requests"] == 0
        assert by_id["cli"]["frontier_requests"] == 1
        assert by_id["unknown"]["cache_hits"] == 1
        assert by_id["cursor"]["estimated_saved_usd"] > 0

    def test_disabled_ledger_returns_empty(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3", enabled=False)
        assert ledger.by_client(days=7) == []

    def test_monthly_spend(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        # 8000 chars -> 2000 tokens -> $0.004 at 0.002/1k
        ledger.record(tier="L6", prompt_chars=4000, completion_chars=4000)
        spend = ledger.frontier_spend_usd_month(price_per_1k_tokens=0.002)
        assert spend == pytest.approx(0.004)


class NullEmbedder:
    async def embed(self, text: str):
        return None


class FakeFrontier:
    api_key = "k"

    def __init__(self):
        self.requests: list[InternalRequest] = []

    async def execute(self, request, *, escalated_from, local_confidence):
        self.requests.append(request)
        return InternalResponse(
            content="Frontier answer.",
            model="gpt-x",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                latency_ms=5,
                confidence=local_confidence,
                escalated_from=escalated_from,
            ),
        )


def _low_confidence_router(tmp_path, ledger, frontier, **kwargs) -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def weak_execute(request: InternalRequest) -> InternalResponse:
        # Short answer scores low confidence and triggers escalation.
        return InternalResponse(
            content="idk",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    executor.execute = weak_execute  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NullEmbedder(), enabled=False),
        ollama=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        usage_ledger=ledger,
        frontier_price_per_1k_tokens=0.002,
        **kwargs,
    )


def _request(text: str, client_id: str | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        meta=RequestMeta(client_id=client_id),
    )


class TestSoftBudget:
    @pytest.mark.asyncio
    async def test_soft_crossing_serves_with_warning(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        # Prior spend: 44k chars -> 11k tokens -> $0.022, clearly past the
        # $0.02 soft line (80% of $0.025) but under the hard cap.
        ledger.record(tier="L6", prompt_chars=22_000, completion_chars=22_000)
        router = _low_confidence_router(
            tmp_path,
            ledger,
            FakeFrontier(),
            frontier_daily_budget_usd=0.025,
            frontier_soft_budget_ratio=0.8,
        )

        response = await router.route(_request("hard question needing escalation"))

        assert response.daari_meta.tier == "L6"
        assert response.daari_meta.warning == "frontier_budget_warning"

    @pytest.mark.asyncio
    async def test_hard_cap_still_blocks(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        ledger.record(tier="L6", prompt_chars=40_000, completion_chars=40_000)  # $0.04
        router = _low_confidence_router(
            tmp_path,
            ledger,
            FakeFrontier(),
            frontier_daily_budget_usd=0.025,
        )

        response = await router.route(_request("hard question needing escalation"))

        assert response.daari_meta.tier == "L3"
        assert response.daari_meta.warning == "frontier_budget_exceeded"

    @pytest.mark.asyncio
    async def test_monthly_hard_cap_blocks(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        ledger.record(tier="L6", prompt_chars=40_000, completion_chars=40_000)  # $0.04
        router = _low_confidence_router(
            tmp_path,
            ledger,
            FakeFrontier(),
            frontier_monthly_budget_usd=0.03,
        )

        response = await router.route(_request("hard question needing escalation"))

        assert response.daari_meta.tier == "L3"
        assert response.daari_meta.warning == "frontier_budget_exceeded"

    @pytest.mark.asyncio
    async def test_under_soft_line_no_warning(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        router = _low_confidence_router(
            tmp_path,
            ledger,
            FakeFrontier(),
            frontier_daily_budget_usd=100.0,
        )

        response = await router.route(_request("hard question needing escalation"))

        assert response.daari_meta.tier == "L6"
        assert response.daari_meta.warning is None

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.frontier.monthly_budget_usd == 0.0
        assert settings.frontier.soft_budget_ratio == 0.8
        assert settings.frontier.scrub_pii is False


class TestClientAttributionThroughRouter:
    @pytest.mark.asyncio
    async def test_client_id_lands_in_ledger(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

        async def good_execute(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="A thorough and complete answer to the question posed here.",
                model="llama3.2:3b",
                daari_meta=DaariMeta(
                    tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
                ),
            )

        executor.execute = good_execute  # type: ignore[method-assign]
        router = Router(
            cache=ExactCache(str(tmp_path / "l0"), enabled=False),
            semantic_cache=SemanticCache(str(tmp_path / "l1"), NullEmbedder(), enabled=False),
            ollama=executor,
            metrics=Metrics(),
            frontier=None,
            frontier_enabled=False,
            usage_ledger=ledger,
        )

        await router.route(_request("please summarize the module", client_id="cursor"))

        clients = ledger.by_client(days=1)
        assert clients and clients[0]["client_id"] == "cursor"


class TestPiiScrubThroughRouter:
    @pytest.mark.asyncio
    async def test_outbound_l6_copy_scrubbed(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        frontier = FakeFrontier()
        router = _low_confidence_router(
            tmp_path, ledger, frontier, frontier_scrub_pii=True
        )

        await router.route(
            _request("Contact bob@example.com about this hard question please")
        )

        sent = frontier.requests[0]
        assert all("bob@example.com" not in (m.content or "") for m in sent.messages)
        assert any("<email-1>" in (m.content or "") for m in sent.messages)

    @pytest.mark.asyncio
    async def test_disabled_by_default(self, tmp_path):
        ledger = UsageLedger(tmp_path / "usage.sqlite3")
        frontier = FakeFrontier()
        router = _low_confidence_router(tmp_path, ledger, frontier)

        await router.route(
            _request("Contact bob@example.com about this hard question please")
        )

        sent = frontier.requests[0]
        assert any("bob@example.com" in (m.content or "") for m in sent.messages)
