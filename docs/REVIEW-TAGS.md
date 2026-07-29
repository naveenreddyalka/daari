# Fable re-verification tags (post Aug 5)

Commits on backlog work are tagged so a stronger model can re-verify each slice:

| Tag pattern | Meaning |
|-------------|---------|
| `fable-review/135-N-<slug>` | Issue #135 Redis L1 — discrete verification checkpoint |

## #135 Redis L1 — tagged slices (2026-07-27)

| Tag | Commit focus | Triple verify |
|-----|--------------|---------------|
| `fable-review/135-1-impl` | `RedisSemanticCache` + unit tests | unit ✅ |
| `fable-review/135-2-wire` | settings + `_build_l1_cache` wiring | unit ✅ |
| `fable-review/135-3-verify` | integration + `scripts/smoke_redis_l1.py` | unit + integration + live smoke ✅ |

## #136 OIDC JWKS SSO — tagged slices (2026-07-28)

| Tag | Commit focus | Triple verify |
|-----|--------------|---------------|
| `fable-review/136-1-jwks` | JWKS verify + unit | unit ✅ |
| `fable-review/136-2-wire` | settings + admin gate + session | unit ✅ |
| `fable-review/136-3-verify` | middleware + integration + smoke | unit + integration + live ✅ |

```bash
git checkout fable-review/136-1-jwks
pip install 'daari[oidc]'  # or PyJWT[crypto]
pytest tests/unit/test_oidc_jwks.py -q

git checkout fable-review/136-2-wire
pytest tests/unit/test_oidc_jwks.py tests/unit/test_sso_wiring.py -q

git checkout fable-review/136-3-verify
pytest tests/unit/test_oidc_jwks.py tests/integration/test_oidc_sso_gateway.py -q
python scripts/smoke_oidc_sso.py
```

Re-verify after Aug 5:

```bash
git checkout fable-review/135-1-impl
pytest tests/unit/test_redis_semantic.py -q

git checkout fable-review/135-2-wire
pytest tests/unit/test_redis_cache.py tests/unit/test_redis_semantic.py -q

git checkout fable-review/135-3-verify
pytest tests/unit/test_redis_semantic.py tests/unit/test_redis_cache.py tests/integration/test_redis_l1_gateway.py -q
python scripts/smoke_redis_l1.py
```

For each tagged commit, re-run **three** verification approaches:

1. **Unit** — `pytest tests/unit/... -q`
2. **Integration** — `pytest -m integration` and/or gateway ASGI tests
3. **Live/smoke** — hit a running daemon (`/health`, `/v1/chat/completions` or `daari` prompt path)

## #141 Web UI API key — tagged slices (2026-07-29)

| Tag | Commit focus | Triple verify |
|-----|--------------|---------------|
| `fable-review/141-1-auth` | toolbar `#api-key` + Authorization on fetches | npm test ✅ |
| `fable-review/141-2-verify` | smoke + docs | unit + smoke ✅ |

```bash
git checkout fable-review/141-2-verify
cd packages/web-ui && npm test
cd ../.. && python scripts/smoke_webui_auth.py
pytest tests/unit/test_config_editor.py -q
```

Do not delete these tags until Fable review is recorded on the linked issue.
