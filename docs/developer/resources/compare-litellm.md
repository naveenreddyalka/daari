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
(18 Oct 2026) is **GA**. After trust, image-scan hygiene, and gzip off-loop
compression backports, the stable comparison floor is
**[1.106.6 GA](https://github.com/BerriAI/litellm/releases/tag/v1.106.6)**
(28 Oct 2026; prior floors
[1.106.5](https://github.com/BerriAI/litellm/releases/tag/v1.106.5) on
27 Oct 2026 and
[1.106.4](https://github.com/BerriAI/litellm/releases/tag/v1.106.4) on
25 Oct 2026; also backported as 1.103.9 / 1.104.7 / 1.105.5). The 1.106 cut
includes a native
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
Stay on LiteLLM **1.106.6** (or skip LiteLLM entirely). Treat 1.107.0 as
unsafe / do-not-install — not a feature comparison bar. Do **not** advertise
compromised 1.107 watchables as safe.

daari does **not** depend on LiteLLM at runtime; the local-first install path
never pulled the poisoned artifact.

## LiteLLM 1.108.0-rc.1 (parity RC, not GA)

LiteLLM
[v1.108.0-rc.1](https://github.com/BerriAI/litellm/releases/tag/v1.108.0-rc.1)
(29 Oct 2026) is a **prerelease** — do not promote it to the GA floor. It only
brings the 1.106.x patch line (gzip scoping / off-loop compression) onto the
1.108 RC train: a **parity** patch onto those 1.106.x fixes, **not a feature**
cut. Stable comparison remains **1.106.6 GA**.

## LiteLLM 1.109-dev watch

LiteLLM
[v1.109.0-dev.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-dev.1)
(28 Oct 2026) is a **prerelease** — do not promote it to the GA floor (stable
comparison remains **1.106.6 GA**). Watchables and daari's stance:

- **Mid-stream fallback continuation** — LiteLLM can keep a streaming chat
  going on a configured fallback mid-answer; daari already emits stream
  partials on the active hop, but mid-stream hop continuation after upstream
  death is a next gap (not claimed here).
- **`LITELLM_OFFLINE_MODE`** — one switch to disable outbound fetches; daari is
  already local-first by default, so this is a naming/ergonomics watch rather
  than a missing trust floor.
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
  daari (no Lens / hosted hub parity).

Measured on the same Ollama corpus: [benchmark vs LiteLLM](benchmark-vs-litellm.md). Short matrix: [compare](compare.md).
