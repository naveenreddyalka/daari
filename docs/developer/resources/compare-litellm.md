# daari vs LiteLLM

LiteLLM is a **provider gateway**: one OpenAI-shaped API in front of 100+ cloud models. daari is a **local cost optimizer**: cache, tools, and Ollama/MLX first, frontier last.

| | LiteLLM | daari |
|--|---------|-------|
| Job | Talk to many remote providers | Keep repeat agent work on your machine |
| Default path | Cloud / configured backends | L0/L1 cache → tools → local → L6 |
| Cache | Optional Redis/Qdrant | Built-in exact + semantic, measured false-hit rate |
| IDE setup | DIY | `daari setup cursor` / Claude Code / JetBrains / VS Code |
| License | MIT-class (OSI) | Apache 2.0 (OSI) |
| Stars / mindshare | Category default | New |

**Pick LiteLLM** if you need 100 providers and virtual keys across a team.

**Pick daari** if Cursor or Claude Code is burning frontier tokens on work a cache or a 3B local model can do, and you want that path to be the default.

They can stack: daari for local $0 tiers, LiteLLM (or OpenRouter) as one L6 slot.

## LiteLLM 1.104 GA (local parity)

LiteLLM [v1.104.0](https://docs.litellm.ai/release_notes/v1.104.0/v1-104-0)
(3 Oct 2026) tightened a few gateway gates. daari already matches these
**on-device** without sending transcripts off-box:

| LiteLLM 1.104 | daari today |
|---------------|-------------|
| Refuse weak/unset master key at start | Same: refuse weak/unset master key (sandbox hatch for local demos) |
| Native compact-to-fit across conversation APIs | Opt-in `routing.compact_to_fit` trims droppable turns before L6; successful trims record `tokens_before` / `tokens_after` on-device (stats/Prometheus: `compact_to_fit_tokens_dropped`) |
| MCP key grant / tool permissions (`require_key_mcp_access_defined`) | Opt-in `integrations.mcp_policy.require_key_access_defined` fail-closed when the virtual key has no MCP grant |

**stdio MCP off by default** in LiteLLM is N/A for daari today (no stdio MCP
transport); watch if a buyer asks. A2A and admin UI stay demand-triggered.

## LiteLLM 1.105.0 GA

LiteLLM [v1.105.0](https://docs.litellm.ai/release_notes/v1.105.0/v1-105-0)
(11 Oct 2026) is **GA**. It includes proxy Decisions routes
(`POST /v1/decisions`, `/v1/systemone`), `litellm.agent()` (coding agents
through the cloud gateway), and Lens / agent traces. daari already serves
`/v1/decisions` and `/v1/systemone` on-box.

`litellm.agent()` and Lens are a cloud agent control plane. daari does **not**
ship Lens or a hosted agent runner. Responses `multi_agent`
forwards to frontier (L6) when enabled, and nested agent token rows land on
the local usage ledger. That path skips local tiers. Requests without
`multi_agent` still take cache → tools → Ollama/MLX before frontier.

Microsoft 365 MCP catalog and Straiker v3 fail-closed routing also landed in
this GA cut. daari does **not** ship those.

## LiteLLM 1.106.0 GA

LiteLLM [v1.106.0](https://github.com/BerriAI/litellm/releases/tag/v1.106.0)
(18 Oct 2026) is **GA**. The 1.106.x line closed with
**[1.106.7](https://github.com/BerriAI/litellm/releases/tag/v1.106.7)**
(final 1.106.x patch after
[1.106.6](https://github.com/BerriAI/litellm/releases/tag/v1.106.6) on
28 Oct 2026; prior floors
[1.106.5](https://github.com/BerriAI/litellm/releases/tag/v1.106.5) on
27 Oct 2026 and
[1.106.4](https://github.com/BerriAI/litellm/releases/tag/v1.106.4) on
25 Oct 2026; also backported as 1.103.9 / 1.104.7 / 1.105.5). The **current
stable comparison floor** is **[1.109.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.1)**
(2026-11-12) — see below. The 1.106 cut includes a native
[decision-model guardrail](https://docs.litellm.ai/docs/proxy/guardrails/decision_model)
(`guardrail: decision_model`): yes/no questions against any `/v1/decisions`
model, blocking or logging at a probability threshold.

**1.106.3–1.106.4 trust / image hygiene:** LiteLLM rotated the image **cosign**
signing key (commit [`e82a3c6`](https://github.com/BerriAI/litellm/commit/e82a3c6))
— buyers still verifying with the old `cosign.pub` will fail — **removed the
eMudhra / emSign root CAs** from trusted bundles, and in **1.106.4** scrubbed
image-scan noise (brotli 1.2.0, emSign ECC Root CA - G3, unused lockfile
packages). daari's local-first stance is independent of LiteLLM images; egress
TLS defaults `upstream.distrust_emudhra_ca: true` (see
[doctor-health](../guides/operations/doctor-health.md) `egress_tls_trust`) and
the Docker image build strips the same roots from certifi + the system CA
store so scanners match runtime distrust without pulling LiteLLM. **1.106.6**
scopes gzip and moves compression off the event loop — parity daari already
ships on-box.

daari does **not** ship a decision-model guardrail yet. Heuristic / regex
guardrails plus the on-box `/v1/decisions` path remain the local route for
operators who pull clef or nimble. daari also does **not** ship LiteLLM's
cosign image signing, one-command Docker quickstart, or JWT
`auto_register_map_existing_key`. stdio MCP stays N/A (no stdio transport).

## LiteLLM 1.107.0 compromise (do not install)

On 2026-10-21, LiteLLM **v1.107.0** PyPI wheels and the official Docker image
were **compromised** with an infostealer and RAT
([Aikido write-up](https://www.aikido.dev/blog/litellm-compromised-infostealer-rat)).
PyPI quarantined the version; the Docker image was removed from Docker Hub /
GHCR. Indicators include `/tmp/.pc_once_*` and `/tmp/remote_code_loader.lock`.

**Do not** `pip install litellm==1.107.0` or pull `litellm/litellm:1.107.0`.
Stay on LiteLLM **1.109.1** (or skip LiteLLM entirely). Treat 1.107.0 as
unsafe / do-not-install — not a feature comparison bar. Do **not** advertise
compromised 1.107 watchables as safe.

daari does **not** depend on LiteLLM at runtime; the local-first install path
never pulled the poisoned artifact.

## LiteLLM 1.108 LTS (history)

LiteLLM
**[v1.108.2](https://github.com/BerriAI/litellm/releases/tag/v1.108.2)**
(2026-11-06) was **GA / LTS** on the one-month
[LTS pilot](https://docs.litellm.ai/docs/enterprise/lts_pilot) line
([version support](https://docs.litellm.ai/docs/enterprise/version_support);
[blog](https://docs.litellm.ai/blog/release-cadence-and-lts-pilot)). The prior
LTS GA cut was
**[v1.108.0](https://github.com/BerriAI/litellm/releases/tag/v1.108.0)**
(2026-11-04); **1.108.2** was the fixes-only LTS patch (including spend/key
401s while Postgres restarts). The **live LTS patch** is now
**[v1.108.7](https://github.com/BerriAI/litellm/releases/tag/v1.108.7)**
(2026-11-12; Responses bridge `max_tool_calls` action-required + failed-turn
`previous_response_id` rebuild; prior live patch
**[v1.108.6](https://github.com/BerriAI/litellm/releases/tag/v1.108.6)**
carried the [#51254](https://github.com/BerriAI/litellm/pull/51254)
credential-field hygiene fix after
**[v1.108.5](https://github.com/BerriAI/litellm/releases/tag/v1.108.5)** on
2026-11-10). The earlier RC
[v1.108.0-rc.1](https://github.com/BerriAI/litellm/releases/tag/v1.108.0-rc.1)
(29 Oct 2026) was a **parity** cut of the 1.106.x gzip / off-loop compression
fixes onto the 1.108 train — not a feature ship — and is superseded by the
stable tags. **1.106.7** remains the final 1.106.x patch; do **not** treat
compromised **1.107.0** as a support window. The **stable comparison floor**
moved to **[1.109.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.1)**
(see below); keep 1.108.7 for LTS-pin buyers only.

**1.108.7 action-required `max_tool_calls`:** LiteLLM fails closed on
Responses→chat bridge params like `max_tool_calls` unless `drop_params` is
on. daari declares `max_tool_calls` on the Responses request, never smuggles
it into chat/Anthropic L6 payloads, and lists it in `daari_meta.dropped_params`
when set — no silent discard and no Bedrock/Claude 400s.

**1.108.7 failed-turn `previous_response_id`:** LiteLLM skips failed turns when
rebuilding a Responses session from `previous_response_id`. daari rejects
`previous_response_id` chains that point at a `failed` or `cancelled` store
row with HTTP 400 (completed priors stay chainable) — honesty without a
proxy control-plane flag.

**LTS pilot and Tuesday cadence are live** (not pending): LiteLLM pauses the
usual four-most-recent-stable-lines patch window on this 1.108 LTS line, and
RC / stable cuts publish on **Tuesday** mornings instead of Saturday
([release cycle](https://docs.litellm.ai/docs/proxy/release_cycle)). That is
competitor ops context, not a daari upgrade path: daari is local-first with
**no LiteLLM runtime** dependency and no weekly proxy release train to pin
against.

## LiteLLM 1.109 GA

LiteLLM
**[v1.109.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.1)**
(2026-11-12) is **GA** and the current **stable comparison floor** (emergency
credential-field hygiene; see
[#51254](https://github.com/BerriAI/litellm/pull/51254)). Prior
**[v1.109.0](https://github.com/BerriAI/litellm/releases/tag/v1.109.0)**
(2026-11-11) and earlier
[v1.109.0-rc.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-rc.1),
[v1.109.0-dev.2](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-dev.2),
and
[v1.109.0-dev.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-dev.1)
builds are superseded. The live LTS patch on the prior line remains
**[1.108.7](https://github.com/BerriAI/litellm/releases/tag/v1.108.7)**
(2026-11-12). Feature notes and daari's stance:

- **Client credential-field hygiene** — LiteLLM #51254 blocked client bodies
  from overriding admin deployment credential fields (`tenant_id`,
  `client_id`, `client_secret`, …) and smuggling `os.environ/` / `oidc/` /
  `secret://` refs into credential resolution. daari is immune by design:
  upstream payloads are built from an explicit allowlist
  (`SamplingParams.openai_payload` / Anthropic bridge), `secret://` refs
  resolve only from operator-owned `Settings` at boot/refresh, and admin
  config PATCH is a validated whitelist with no credential fields. Fenced by
  `tests/unit/test_client_credential_hygiene.py`.

- **Mid-stream fallback continuation** — LiteLLM can keep a streaming chat
  going on a configured fallback mid-answer. daari ships the same on-box via
  opt-in `routing.stream_fallback_continue` (default off): after ≥1 content
  token, a dead local/L6 hop continues on the next tier/slot with the partial
  replayed into the transcript (see
  [routing tiers](../concepts/routing-tiers.md#mid-stream-fallback-continuation)).
- **Daily request + token limits** — 1.109 adds deployment RPD/TPD
  (with `daily_reset_time`) and per-provider/model RPM/TPM on project quotas.
  daari already fences key/team/user `--rpd` / `--user-rpd` and `--tpd` /
  `--user-tpd` on-box (UTC day, estimated tokens at admission); no cloud
  quota plane.
- **`x-litellm-priority`** — request-header priority into LiteLLM admission.
  daari ships the on-box twin as optional `X-Daari-Priority: high|normal|low`
  on the same in-flight gate as key/team `--priority` (boost capped unless
  `server.virtual_keys.allow_request_priority_boost`).
- **Cosign key rotation** — 1.109 images continue under the rotated
  `cosign.pub` introduced in 1.106.3 (commit
  [`e82a3c6`](https://github.com/BerriAI/litellm/commit/e82a3c6)). Buyers still
  verifying with the old key will fail; daari does not ship LiteLLM images.
- **Anthropic `drop_params` / `speed` hygiene** — 1.109 lets
  `drop_params` drop `speed` after Anthropic removed fast mode on older
  Claudes. Related on-box path: opt-in `models.degrade_deprecated_speed`
  strips deprecated `speed` with soft_warning `deprecated_speed_degraded`
  instead of hard-failing after the removal date.
- **`LITELLM_OFFLINE_MODE`** — one switch to disable outbound fetches; daari is
  already local-first by default, so this is naming/ergonomics rather than a
  missing trust floor.
- **`agent_access_default_deny`** — keys with no agent grants reach no agents;
  daari mirrors this on-box via opt-in
  `server.virtual_keys.agent_access_default_deny` (default false): virtual keys
  without `metadata.agents_access` / `allowed_agents` get HTTP 403 on Responses
  `multi_agent.enabled` (same trust floor as MCP
  `integrations.mcp_policy.require_key_access_defined`).
- **`model_info.pricing_provider`** — price a deployment from another
  provider's catalog; daari keeps spend math on-box via local
  `pricing.models` (no catalog fetch required).
- **Admin Chat UI / model hub** — cloud control-plane surface; non-goal for
  daari (no Lens / hosted hub parity claimed).

### 1.109.0 action-required upgrade costs

v1.109.0 ships five **action-required** migration items — honest upgrade-cost
evidence for buyers comparing a LiteLLM bump to staying on daari local-first
(or skipping LiteLLM):

1. **Fallback targets must be lists** — string fallback targets are no longer
   accepted; configs must use list form.
2. **Disk cache backend removed** — `cache_params.type: disk` stops proxy
   startup ([#48114](https://github.com/BerriAI/litellm/pull/48114)); Redis or
   in-memory only.
3. **Hard RPM caps** need
   `optional_pre_call_checks: ["enforce_model_rate_limits"]` or they do not
   enforce.
4. **Gemini 3.6 / 3.5** refuse sampling params unless `drop_params` is set.
5. **Lens** moved to its own Helm chart (no longer bundled with the proxy
   chart).

**Disk cache vs daari L1:** LiteLLM removed the on-disk cache backend entirely
([#48114](https://github.com/BerriAI/litellm/pull/48114)), so a single-box
LiteLLM deploy that relied on `type: disk` must add Redis or accept
in-memory-only. daari's $0 L0/L1 path remains a local **diskcache** by design
— exact + semantic hits survive process restarts without Redis. That is a
factual packaging difference, not a claim that LiteLLM cannot cache.

## LiteLLM 1.110.0-dev.1 watch

LiteLLM
[v1.110.0-dev.1](https://github.com/BerriAI/litellm/releases/tag/v1.110.0-dev.1)
(2026-11-07) is **prerelease watch only** — do **not** promote 1.110 to the
GA floor (stable comparison remains **1.109.1**). Watchables on this channel
include provider-reported `usage.cost`, tenant session affinity, and
Lens-split Helm; daari does **not** claim Lens / hosted Helm parity. Treat
1.110-dev as competitor ops context, not a support window.

Measured on the same Ollama corpus: [benchmark vs LiteLLM](benchmark-vs-litellm.md). Short matrix: [compare](compare.md).
