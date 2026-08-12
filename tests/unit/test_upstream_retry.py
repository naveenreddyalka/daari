"""Bounded retries with backoff for upstream calls (issue #159).

A single transient 429 or connection reset used to fail the whole request, and the
frontier pool burned a provider slot on any exception — including blips a short
backoff would clear.
"""

from __future__ import annotations

import httpx
import pytest

from daari.router.retry import (
    RetryPolicy,
    RetryBudgetExhausted,
    is_retryable,
    retry_after_seconds,
    with_retries,
)


def _status_error(code: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://upstream/v1/chat/completions")
    response = httpx.Response(code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class TestClassification:
    @pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
    def test_transient_status_codes_are_retryable(self, code):
        assert is_retryable(_status_error(code)) is True

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_client_errors_are_not_retryable(self, code):
        """Retrying a bad key or a malformed body just wastes the budget."""
        assert is_retryable(_status_error(code)) is False

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.ConnectError("refused"),
            httpx.ConnectTimeout("slow"),
            httpx.ReadTimeout("slow"),
            httpx.PoolTimeout("full"),
            httpx.RemoteProtocolError("truncated"),
        ],
    )
    def test_transport_failures_are_retryable(self, exc):
        assert is_retryable(exc) is True

    def test_unexpected_errors_are_not_retryable(self):
        assert is_retryable(ValueError("programming error")) is False

    def test_ollama_request_error_is_classified_by_its_status(self):
        """Ollama raises its own error type rather than httpx.HTTPStatusError."""
        from daari.router.router import OllamaRequestError

        assert is_retryable(OllamaRequestError(503, "http://o/api/chat", "busy")) is True
        assert is_retryable(OllamaRequestError(400, "http://o/api/chat", "bad")) is False


class TestRetryAfter:
    def test_numeric_retry_after_is_honored(self):
        assert retry_after_seconds(_status_error(429, {"Retry-After": "7"})) == 7.0

    def test_absent_header_returns_none(self):
        assert retry_after_seconds(_status_error(429)) is None

    def test_garbage_header_is_ignored(self):
        assert retry_after_seconds(_status_error(429, {"Retry-After": "soon"})) is None

    def test_http_date_is_supported(self):
        from email.utils import format_datetime
        from datetime import datetime, timedelta, timezone

        when = datetime.now(timezone.utc) + timedelta(seconds=30)
        value = retry_after_seconds(_status_error(503, {"Retry-After": format_datetime(when)}))
        assert value is not None and 20 <= value <= 31


class TestBackoff:
    def test_delays_grow_exponentially_and_are_capped(self):
        policy = RetryPolicy(attempts=6, base_delay=1.0, max_delay=4.0, jitter=0.0)
        assert [policy.delay_for(n) for n in range(5)] == [1.0, 2.0, 4.0, 4.0, 4.0]

    def test_jitter_stays_within_bounds(self):
        policy = RetryPolicy(attempts=4, base_delay=1.0, max_delay=10.0, jitter=0.5)
        for _ in range(50):
            delay = policy.delay_for(1)
            assert 1.0 <= delay <= 2.0, "equal jitter keeps delay in [d/2, d]"


class TestWithRetries:
    @pytest.mark.asyncio
    async def test_transient_failure_then_success(self):
        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise _status_error(503)
            return "ok"

        slept: list[float] = []
        result = await with_retries(
            flaky,
            policy=RetryPolicy(attempts=3, base_delay=0.01, max_delay=0.02, jitter=0.0),
            sleep=slept.append,
        )
        assert result == "ok"
        assert len(attempts) == 3
        assert slept == [0.01, 0.02]

    @pytest.mark.asyncio
    async def test_permanent_failure_still_raises_the_original_error(self):
        async def broken():
            raise _status_error(500)

        with pytest.raises(httpx.HTTPStatusError):
            await with_retries(
                broken,
                policy=RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0),
                sleep=lambda _: None,
            )

    @pytest.mark.asyncio
    async def test_non_retryable_error_is_not_retried(self):
        attempts = []

        async def unauthorized():
            attempts.append(1)
            raise _status_error(401)

        with pytest.raises(httpx.HTTPStatusError):
            await with_retries(
                unauthorized,
                policy=RetryPolicy(attempts=5, base_delay=0.0, max_delay=0.0, jitter=0.0),
                sleep=lambda _: None,
            )
        assert len(attempts) == 1, "a bad key must fail immediately"

    @pytest.mark.asyncio
    async def test_retry_budget_cannot_exceed_the_deadline(self):
        """A retry that would outlast the request timeout must not be attempted."""
        attempts = []
        clock = iter([0.0, 0.0, 9.9, 9.9])

        async def slow():
            attempts.append(1)
            raise _status_error(503)

        with pytest.raises(httpx.HTTPStatusError):
            await with_retries(
                slow,
                policy=RetryPolicy(attempts=5, base_delay=5.0, max_delay=5.0, jitter=0.0),
                sleep=lambda _: None,
                timeout=10.0,
                monotonic=lambda: next(clock),
            )
        assert len(attempts) == 2, "second retry would land past the 10s deadline"

    @pytest.mark.asyncio
    async def test_retry_after_overrides_computed_backoff(self):
        slept: list[float] = []
        attempts = []

        async def throttled():
            attempts.append(1)
            if len(attempts) == 1:
                raise _status_error(429, {"Retry-After": "2"})
            return "ok"

        await with_retries(
            throttled,
            policy=RetryPolicy(attempts=3, base_delay=0.01, max_delay=0.01, jitter=0.0),
            sleep=slept.append,
        )
        assert slept == [2.0]

    @pytest.mark.asyncio
    async def test_each_retry_is_reported(self):
        seen: list[tuple[int, str]] = []
        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise _status_error(503)
            return "ok"

        await with_retries(
            flaky,
            policy=RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0),
            sleep=lambda _: None,
            on_retry=lambda attempt, exc, delay: seen.append((attempt, type(exc).__name__)),
        )
        assert seen == [(1, "HTTPStatusError"), (2, "HTTPStatusError")]

    @pytest.mark.asyncio
    async def test_operation_runs_once_when_it_succeeds(self):
        """Guards against retry wrappers that duplicate side effects."""
        attempts = []

        async def fine():
            attempts.append(1)
            return "ok"

        assert await with_retries(fine, policy=RetryPolicy(attempts=3)) == "ok"
        assert len(attempts) == 1


class TestPolicyFromSettings:
    def test_disabled_when_attempts_is_one(self):
        policy = RetryPolicy(attempts=1)
        assert policy.enabled is False

    def test_attempts_below_one_is_coerced(self):
        assert RetryPolicy(attempts=0).attempts == 1

    def test_built_from_settings(self):
        from daari.config.settings import Settings

        settings = Settings()
        policy = RetryPolicy.from_settings(settings.upstream.retry)
        assert policy.attempts == settings.upstream.retry.attempts
        assert policy.base_delay == pytest.approx(
            settings.upstream.retry.base_delay_ms / 1000
        )


def test_budget_exhausted_error_is_exported():
    """The pool needs a way to tell "retries done" from "do not retry"."""
    assert issubclass(RetryBudgetExhausted, Exception)
