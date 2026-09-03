"""secret://oauth — OAuth client-credentials upstream auth (issue #321).

No static upstream key on disk: the ref names a token endpoint and a client id,
the client secret comes from an existing secret ref, and daari mints a
short-lived access token that it caches until expiry minus a margin and
re-mints lazily on the next read. Failures name the endpoint, never the secret.
"""

from __future__ import annotations

import base64
import copy
import json
import threading
from urllib.parse import parse_qs

import httpx
import pytest

from daari.config.settings import Settings
from daari.security import secret_refs
from daari.security.secret_refs import (
    RefreshableSecret,
    SecretRefError,
    clear_registered_secrets,
    current_secret,
    parse_oauth_ref,
    redact_secrets,
    resolve_secret_ref,
    resolve_settings_secrets,
)

TOKEN_URL = "https://idp.example.com/oauth/token"
CLIENT_SECRET = "s3cr3t-client-value"


@pytest.fixture(autouse=True)
def _fresh_registry():
    clear_registered_secrets()
    yield
    clear_registered_secrets()


@pytest.fixture
def secret_env(tmp_path):
    env = tmp_path / "idp.env"
    env.write_text(f"IDP_SECRET={CLIENT_SECRET}\n", encoding="utf-8")
    return f"secret://env-file/{env}#IDP_SECRET"


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TokenServer:
    """MockTransport standing in for an IdP token endpoint."""

    def __init__(self, *, expires_in: int | None = 3600, status: int = 200, body=None) -> None:
        self.expires_in = expires_in
        self.status = status
        self.body = body
        self.requests: list[httpx.Request] = []
        self.issued = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "invalid_client"})
        if self.body is not None:
            return httpx.Response(200, content=self.body)
        self.issued += 1
        payload = {"access_token": f"tok-{self.issued}", "token_type": "Bearer"}
        if self.expires_in is not None:
            payload["expires_in"] = self.expires_in
        return httpx.Response(200, json=payload)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def form(self, index: int = -1) -> dict[str, str]:
        parsed = parse_qs(self.requests[index].content.decode())
        return {key: values[0] for key, values in parsed.items()}


def _ref(secret_ref: str, **params: str) -> str:
    query = {"client_id": "daari-svc", "client_secret": secret_ref, **params}
    return f"secret://oauth/{TOKEN_URL}?" + "&".join(f"{k}={v}" for k, v in query.items())


class TestParse:
    def test_parses_all_parameters(self, secret_env):
        grant = parse_oauth_ref(
            _ref(
                secret_env,
                scope="llm.invoke",
                audience="https://api.openai.com",
                resource="urn:r",
                auth="post",
                refresh_margin="120",
            )[len("secret://oauth/") :],
            "ref",
        )
        assert grant.token_url == TOKEN_URL
        assert grant.client_id == "daari-svc"
        assert grant.client_secret_ref == secret_env
        assert grant.scope == "llm.invoke"
        assert grant.audience == "https://api.openai.com"
        assert grant.resource == "urn:r"
        assert grant.auth == "post"
        assert grant.refresh_margin == 120.0

    def test_defaults(self, secret_env):
        grant = parse_oauth_ref(_ref(secret_env)[len("secret://oauth/") :], "ref")
        assert grant.scope is None and grant.audience is None and grant.resource is None
        assert grant.auth == "basic"
        assert grant.refresh_margin == 60.0

    @pytest.mark.parametrize(
        "ref",
        [
            "secret://oauth/not-a-url?client_id=x&client_secret=secret://env-file/a#B",
            f"secret://oauth/{TOKEN_URL}?client_secret=secret://env-file/a#B",
            f"secret://oauth/{TOKEN_URL}?client_id=x",
        ],
    )
    def test_malformed_refs_are_fatal(self, ref):
        with pytest.raises(SecretRefError):
            resolve_secret_ref(ref)

    def test_inline_client_secret_is_rejected(self):
        ref = f"secret://oauth/{TOKEN_URL}?client_id=x&client_secret=plaintext-secret"
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(ref)
        message = str(excinfo.value)
        assert "never inline" in message
        assert "plaintext-secret" not in message

    def test_nested_oauth_secret_is_rejected(self):
        nested = f"secret://oauth/{TOKEN_URL}?client_id=y&client_secret=secret://env-file/a#B"
        ref = f"secret://oauth/{TOKEN_URL}?client_id=x&client_secret={nested}"
        with pytest.raises(SecretRefError):
            resolve_secret_ref(ref)

    def test_bad_auth_or_margin_is_fatal(self, secret_env):
        with pytest.raises(SecretRefError):
            resolve_secret_ref(_ref(secret_env, auth="mtls"))
        with pytest.raises(SecretRefError):
            resolve_secret_ref(_ref(secret_env, refresh_margin="soon"))


class TestGrant:
    def test_happy_path_basic_auth(self, secret_env):
        server = TokenServer()
        clock = FakeClock()
        ref = _ref(
            secret_env, scope="llm.invoke", audience="https://api.openai.com", resource="urn:r"
        )

        token = resolve_secret_ref(ref, transport=server.transport, clock=clock)

        assert token == "tok-1"
        assert isinstance(token, RefreshableSecret) and token.ref == ref
        request = server.requests[0]
        assert request.method == "POST"
        assert str(request.url) == TOKEN_URL
        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
        expected = base64.b64encode(f"daari-svc:{CLIENT_SECRET}".encode()).decode()
        assert request.headers["authorization"] == f"Basic {expected}"
        assert server.form() == {
            "grant_type": "client_credentials",
            "scope": "llm.invoke",
            "audience": "https://api.openai.com",
            "resource": "urn:r",
        }

    def test_post_auth_puts_credentials_in_body(self, secret_env):
        server = TokenServer()
        resolve_secret_ref(_ref(secret_env, auth="post"), transport=server.transport)
        assert "authorization" not in server.requests[0].headers
        form = server.form()
        assert form["client_id"] == "daari-svc"
        assert form["client_secret"] == CLIENT_SECRET
        assert form["grant_type"] == "client_credentials"

    def test_token_and_client_secret_are_registered_for_redaction(self, secret_env):
        server = TokenServer()
        resolve_secret_ref(_ref(secret_env), transport=server.transport)
        scrubbed = redact_secrets(f"bearer tok-1 via {CLIENT_SECRET}")
        assert "tok-1" not in scrubbed
        assert CLIENT_SECRET not in scrubbed

    def test_register_false_still_resolves(self, secret_env):
        server = TokenServer()
        resolve_secret_ref(_ref(secret_env), transport=server.transport, register=False)
        assert "tok-1" in redact_secrets("tok-1")


class TestCache:
    def test_second_resolve_reuses_cached_token(self, secret_env):
        server = TokenServer(expires_in=3600)
        clock = FakeClock()
        ref = _ref(secret_env)
        first = resolve_secret_ref(ref, transport=server.transport, clock=clock)
        clock.advance(1800)
        second = resolve_secret_ref(ref, transport=server.transport, clock=clock)
        assert first == second == "tok-1"
        assert len(server.requests) == 1

    def test_refreshes_inside_margin_before_expiry(self, secret_env):
        server = TokenServer(expires_in=300)
        clock = FakeClock()
        ref = _ref(secret_env)  # default 60s margin
        assert resolve_secret_ref(ref, transport=server.transport, clock=clock) == "tok-1"
        clock.advance(239)
        assert resolve_secret_ref(ref, transport=server.transport, clock=clock) == "tok-1"
        clock.advance(2)  # 241s in: 300 - 60 = 240 crossed
        assert resolve_secret_ref(ref, transport=server.transport, clock=clock) == "tok-2"
        assert len(server.requests) == 2

    def test_custom_refresh_margin(self, secret_env):
        server = TokenServer(expires_in=300)
        clock = FakeClock()
        ref = _ref(secret_env, refresh_margin="200")
        resolve_secret_ref(ref, transport=server.transport, clock=clock)
        clock.advance(101)
        assert resolve_secret_ref(ref, transport=server.transport, clock=clock) == "tok-2"

    def test_missing_expires_in_uses_conservative_default(self, secret_env):
        server = TokenServer(expires_in=None)
        clock = FakeClock()
        ref = _ref(secret_env)
        resolve_secret_ref(ref, transport=server.transport, clock=clock)
        clock.advance(3600 - 61)
        assert resolve_secret_ref(ref, transport=server.transport, clock=clock) == "tok-1"
        clock.advance(2)
        assert resolve_secret_ref(ref, transport=server.transport, clock=clock) == "tok-2"

    def test_cache_is_per_ref(self, secret_env):
        server = TokenServer()
        resolve_secret_ref(_ref(secret_env, scope="a"), transport=server.transport)
        resolve_secret_ref(_ref(secret_env, scope="b"), transport=server.transport)
        assert len(server.requests) == 2

    def test_concurrent_first_resolve_mints_once(self, secret_env):
        server = TokenServer()
        ref = _ref(secret_env)
        results: list[str] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                results.append(resolve_secret_ref(ref, transport=server.transport))
            except Exception as exc:  # pragma: no cover - surfaced via assert
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not errors
        assert set(results) == {"tok-1"}
        assert len(server.requests) == 1


class TestErrors:
    def test_non_2xx_names_endpoint_not_secret(self, secret_env):
        server = TokenServer(status=401)
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(_ref(secret_env), transport=server.transport)
        message = str(excinfo.value)
        assert TOKEN_URL in message and "401" in message
        assert CLIENT_SECRET not in message
        assert "daari-svc" not in message

    def test_non_json_body_is_fatal(self, secret_env):
        server = TokenServer(body=b"<html>oops</html>")
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(_ref(secret_env), transport=server.transport)
        assert "non-JSON" in str(excinfo.value)

    def test_missing_access_token_is_fatal(self, secret_env):
        server = TokenServer(body=json.dumps({"token_type": "Bearer"}).encode())
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(_ref(secret_env), transport=server.transport)
        assert "no access_token" in str(excinfo.value)

    def test_transport_error_is_fatal_and_named(self, secret_env):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(_ref(secret_env), transport=httpx.MockTransport(boom))
        assert "ConnectError" in str(excinfo.value)
        assert TOKEN_URL in str(excinfo.value)

    def test_unresolvable_client_secret_surfaces_nested_ref(self, tmp_path):
        missing = f"secret://env-file/{tmp_path}/absent.env#K"
        server = TokenServer()
        with pytest.raises(SecretRefError) as excinfo:
            resolve_secret_ref(_ref(missing), transport=server.transport)
        assert missing in str(excinfo.value)
        assert not server.requests

    def test_failure_is_not_cached(self, secret_env):
        server = TokenServer(status=503)
        ref = _ref(secret_env)
        with pytest.raises(SecretRefError):
            resolve_secret_ref(ref, transport=server.transport)
        server.status = 200
        assert resolve_secret_ref(ref, transport=server.transport) == "tok-1"


class TestRefreshableSecret:
    def test_behaves_as_str(self):
        token = RefreshableSecret("abc", "secret://oauth/x")
        assert token == "abc"
        assert f"Bearer {token}" == "Bearer abc"
        assert json.dumps({"k": token}) == '{"k": "abc"}'
        assert hash(token) == hash("abc")

    def test_survives_deepcopy(self):
        token = RefreshableSecret("abc", "secret://oauth/x")
        clone = copy.deepcopy({"keys": [token]})["keys"][0]
        assert clone == "abc"
        assert isinstance(clone, RefreshableSecret) and clone.ref == "secret://oauth/x"

    def test_current_secret_passes_plain_values_through(self):
        assert current_secret("plain") == "plain"
        assert current_secret(None) is None
        assert current_secret(RefreshableSecret("orphan")) == "orphan"


class TestRuntimeRefresh:
    @pytest.fixture
    def live(self, monkeypatch, secret_env):
        server = TokenServer(expires_in=300)
        clock = FakeClock()
        monkeypatch.setattr(secret_refs, "_default_transport", server.transport)
        monkeypatch.setattr(secret_refs, "_now", clock)
        return server, clock, _ref(secret_env)

    def test_settings_resolve_to_refreshable_token(self, live):
        server, clock, ref = live
        settings = Settings.model_validate(
            {
                "frontier": {"providers": [{"id": "openai", "keys": [ref]}]},
                "enterprise": {"shared_cache_token": ref},
            }
        )
        resolved = resolve_settings_secrets(settings)
        assert resolved == [ref, ref]
        key = settings.frontier.providers[0].keys[0]
        assert key == "tok-1" and isinstance(key, RefreshableSecret)
        assert settings.enterprise.shared_cache_token == "tok-1"
        assert len(server.requests) == 1  # same ref, cached across both fields

        clock.advance(250)
        assert current_secret(key) == "tok-2"
        assert current_secret(settings.enterprise.shared_cache_token) == "tok-2"
        assert len(server.requests) == 2

    def test_frontier_pool_picks_fresh_token_per_attempt(self, live):
        from daari.router.frontier import FrontierExecutor
        from daari.router.frontier_pool import ProviderSlot

        server, clock, ref = live
        key = resolve_secret_ref(ref)
        slot = ProviderSlot(
            id="openai",
            executor=FrontierExecutor(
                base_url="https://api.openai.com/v1", default_model="gpt", api_key=key
            ),
            keys=[key],
        )
        assert slot.pick_key() == "tok-1"
        clock.advance(250)
        assert slot.pick_key() == "tok-2"
        assert slot.pick_key() == "tok-2"
        assert len(server.requests) == 2

    def test_frontier_pool_from_single_refreshes_too(self, live):
        from daari.router.frontier import FrontierExecutor
        from daari.router.frontier_pool import FrontierPool

        server, clock, ref = live
        key = resolve_secret_ref(ref)
        pool = FrontierPool.from_single(
            FrontierExecutor(base_url="https://api.openai.com/v1", default_model="gpt", api_key=key)
        )
        clock.advance(250)
        assert pool.slots[0].pick_key() == "tok-2"

    @pytest.mark.asyncio
    async def test_frontier_pool_fails_closed_when_refresh_fails(self, live):
        from daari.gateway.internal import InternalRequest, Message
        from daari.router.frontier import FrontierExecutor
        from daari.router.frontier_pool import FrontierPool, ProviderSlot

        server, clock, ref = live
        key = resolve_secret_ref(ref)
        executor = FrontierExecutor(
            base_url="https://api.openai.com/v1", default_model="gpt", api_key=key
        )
        pool = FrontierPool(slots=[ProviderSlot(id="openai", executor=executor, keys=[key])])
        clock.advance(250)
        server.status = 503
        request = InternalRequest(model="gpt", messages=[Message(role="user", content="hi")])
        with pytest.raises(RuntimeError) as excinfo:
            await pool.execute(request, escalated_from="L3", local_confidence=0.1)
        assert "openai:SecretRefError" in str(excinfo.value)
        # The stale token was never rotated onto the executor for a send.
        assert executor.api_key == "tok-1"

    def test_org_clients_send_fresh_bearer(self, live):
        from daari.enterprise.client import OrgCacheClient, OrgLearningClient

        server, clock, ref = live
        token = resolve_secret_ref(ref)
        cache = OrgCacheClient(base_url="https://org.example.com", token=token)
        learning = OrgLearningClient(base_url="https://org.example.com", token=token)
        assert cache._auth_headers()["Authorization"] == "Bearer tok-1"
        clock.advance(250)
        assert cache._auth_headers()["Authorization"] == "Bearer tok-2"
        assert learning._auth_headers()["Authorization"] == "Bearer tok-2"
        assert OrgCacheClient(base_url="x", token="static")._auth_headers() == {
            "Authorization": "Bearer static"
        }
