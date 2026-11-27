# daari vs LiteLLM

LiteLLM is a **provider gateway**: one OpenAI-shaped API in front of 100+ cloud models. daari is a **local cost optimizer**: cache, tools, and Ollama/MLX first, frontier last. Local engine floor for OpenAI-compat slots is [llama.cpp v1.0.0](https://github.com/ggml-org/llama.cpp/releases/tag/v1.0.0) ([operator guide](../guides/configuration/llamacpp-local-tier.md)).

| | LiteLLM | daari |
|--|---------|-------|
| Job | Talk to many remote providers | Keep repeat agent work on your machine |
| Default path | Cloud / configured backends | L0/L1 cache → tools → local → L6 |
| Cache | Optional Redis/Qdrant | Built-in exact + semantic, measured false-hit rate |
| Router core | Rust router core behind a Python host (1.110+; Python core deleted) | Pure-Python single process, `pip install`, pdb-debuggable |
| Spend accounting | SpendLogs ledger is the default path (1.110+) | On-box SQLite usage ledger (per-key / team / user / tier rows; Postgres is the optional control-plane store) |
| FIPS mode | Startup gate + PBKDF2 / KBKDF hashes (1.110+) | **No FIPS gate** — watch row, not a parity claim |
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
the local usage ledger — priced per declared subagent model from
`pricing.models` when the provider omits `usage.cost` (#1553). That path
skips local tiers. Requests without
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
stable comparison floor** is **[1.111.0](https://github.com/BerriAI/litellm/releases/tag/v1.111.0)**
(2026-11-25) — see below. The 1.106 cut includes a native
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
Stay on LiteLLM **1.111.0** stable or **1.108.17** LTS (or skip LiteLLM
entirely). Treat 1.107.0 as
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
**[v1.108.17](https://github.com/BerriAI/litellm/releases/tag/v1.108.17)**
(2026-11-24; streamed tool calls with end-only arguments, `chat-latest`
first-prompt 400, FLAC duration billing, OpenAI Agents session $0-logging
fix). Prior LTS patches retained for history:
**[v1.108.16](https://github.com/BerriAI/litellm/releases/tag/v1.108.16)**
(2026-11-23; MCP DCR opt-in backport, `anthropic-version: 2026-10-21`
sampling, Gradium TTS),
**[v1.108.11](https://github.com/BerriAI/litellm/releases/tag/v1.108.11)**
(2026-11-17; 22 fixes-only PRs),
**[v1.108.10](https://github.com/BerriAI/litellm/releases/tag/v1.108.10)**
(2026-11-16; wildcard `base_model` pricing, PDF-URL / file-part async),
**[v1.108.8](https://github.com/BerriAI/litellm/releases/tag/v1.108.8)**
(2026-11-13; Azure `/v1/decisions`, file-id ownership spelling, MCP
`mcp_all` scope grant),
**[v1.108.7](https://github.com/BerriAI/litellm/releases/tag/v1.108.7)**
(2026-11-12; Responses `max_tool_calls` + failed-turn
`previous_response_id`),
**[v1.108.6](https://github.com/BerriAI/litellm/releases/tag/v1.108.6)**
([#51254](https://github.com/BerriAI/litellm/pull/51254) credential-field
hygiene), and
**[v1.108.5](https://github.com/BerriAI/litellm/releases/tag/v1.108.5)**
(2026-11-10). The earlier RC
[v1.108.0-rc.1](https://github.com/BerriAI/litellm/releases/tag/v1.108.0-rc.1)
(29 Oct 2026) was a **parity** cut of the 1.106.x gzip / off-loop compression
fixes onto the 1.108 train — not a feature ship — and is superseded by the
stable tags. **1.106.7** remains the final 1.106.x patch; do **not** treat
compromised **1.107.0** as a support window. The **stable comparison floor**
moved to **[1.111.0](https://github.com/BerriAI/litellm/releases/tag/v1.111.0)**
(see below); keep **1.108.17** for LTS-pin buyers only.

**1.108.17 LTS highlights:** streamed tool calls whose arguments arrive only
on the final chunk are now assembled instead of dropped; the
`chat-latest` alias returns a 400 on the first prompt instead of a silent
fallback; FLAC audio is billed from real duration; OpenAI Agents sessions no
longer log $0 rows. daari's stance: the Responses bridge already
accumulates tool-call deltas per index before emitting `function_call` items
(chat streams pass provider deltas through unchanged, so end-only arguments
reach the client intact); speech / ASR duration billing ([#2250](https://github.com/naveenreddyalka/daari/issues/2250))
prices from upstream `usage` or audio duration regardless of container; local
Ollama / MLX speech and ASR stay **$0** on the ledger, and Responses
`multi_agent` nested rows land on the same SQLite ledger (never a silent $0
row for a billed hop).

**1.108.16 MCP DCR opt-in (backport):** LiteLLM's MCP gateway can register
itself with upstream OAuth servers via Dynamic Client Registration when an
operator opts in
([#53059](https://github.com/BerriAI/litellm/pull/53059) →
[#53180](https://github.com/BerriAI/litellm/pull/53180)). daari ships **no
hosted DCR control plane**; on-box MCP OAuth uses operator-pinned
`secret://oauth` client credentials or per-server OBO token exchange, plus
RFC 9728 protected-resource discovery when opted in (see
[MCP clients](../guides/clients/mcp.md)). DCR is a watch row, not a parity
claim.

**1.108.16 `anthropic-version: 2026-10-21` sampling:** LiteLLM drops or
rejects `temperature` / `top_p` / `top_k` under the new Anthropic API version
([#53395](https://github.com/BerriAI/litellm/pull/53395)). daari already
strips the trio on that header (`apply_anthropic_version_sampling_compat`) and
for Fable / Mythos ids via builtin `frontier.param_compat` — see the
[sampling watch](#anthropic-api-version-2026-10-21-sampling-watch-2384)
below.

**1.108.16 provider catalog (LTS):** Gradium native `/v1/audio/speech`,
Gnani Prisma transcription, Perplexity Orchestrator, `gemini-decision-1` on
`/v1/decisions`, Gemini `video_url` parts kept, thought-signature replay,
batch-embedding spend from `usageMetadata`, `/v1/decisions` through the
`litellm_proxy` provider, and Azure Foundry `/openai/v1` chat routing
backports; Responses tool-call replay plus cut-stream input billing honesty.
daari makes **no Gradium / Gnani / Perplexity provider claim**: local
speech / OCR / ASR paths stay $0 on-box (Ollama Phonon / `lfm3-audio`,
llama.cpp `drama-3`, Kokoro via `tts.base_url`; see
[tts](../guides/backends/tts.md) and [asr](../guides/backends/asr.md)), and
`/v1/decisions` prefers local System One before any Gemini decision model.
Gemini `video_url` parts and thought-signature replay ride the L6 leg
unchanged.

**1.108.10 wildcard `base_model` pricing:** LiteLLM stopped a `base_model:
"*"` / wildcard deployment from pinning the cost ladder at $0 — the priced
response model now wins
([#47497](https://github.com/BerriAI/litellm/pull/47497) /
[#51412](https://github.com/BerriAI/litellm/pull/51412)). daari never had
the trap: spend is priced from the **served** model via longest-prefix
`matching_model_key` against `pricing.models`, so a wildcard slot cannot
zero the local ledger.

**1.108.10 PDF-URL / file-part async:** async chat with `file` parts
(Codestral) and PDF-URL downloads moved off the event loop
([#49176](https://github.com/BerriAI/litellm/pull/49176) /
[#51860](https://github.com/BerriAI/litellm/pull/51860)); versioned Claude
`max_tokens` on Vertex AI landed alongside
([#40376](https://github.com/BerriAI/litellm/pull/40376) /
[#51863](https://github.com/BerriAI/litellm/pull/51863)). daari's L0–L5
tiers never download remote PDFs on the serving loop; file bytes come from
the local FileStore, and only an explicit L6 hop forwards provider file
parts.

**1.108.8 Azure Decisions vs local-first:** LiteLLM fixed 400s on
`/v1/decisions` for `azure/` deployments (keyless Entra /
[#51460](https://github.com/BerriAI/litellm/pull/51460)). daari already serves
`/v1/decisions` on-box and prefers local System One before any frontier hop;
Azure (or other L6) is optional egress, not the default Decisions path.

**1.108.8 file-id ownership spelling:** LiteLLM canonicalizes alternate
Gemini file-id spellings (`files/<id>`, URL forms) so ownership checks do not
miss siblings
([#51503](https://github.com/BerriAI/litellm/pull/51503)). daari stores
OpenAI-shaped `file-{hex}` ids with per-key `owner_key_id` fencing on list /
read / delete; it does **not** rewrite provider-native `files/` URL aliases
into local ids — operators who need Gemini alias folding still need that
provider's spelling on the L6 leg.

**1.108.8 `mcp_all` scope wildcard:** LiteLLM accepts servers that answer
OAuth with a catch-all `mcp_all` grant plus detailed scopes without a
sign-in loop ([#51578](https://github.com/BerriAI/litellm/pull/51578)).
daari has no LiteLLM-named `mcp_all` sentinel; on-box MCP grants use
fnmatch allow/deny globs (and optional
`integrations.mcp_policy.require_key_access_defined`), so a `*` allow is the
honest catch-all without a SaaS connect loop.

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
(2026-11-12) is **GA** and was the stable comparison floor until 1.110.0 /
1.111.0 shipped (emergency credential-field hygiene; see
[#51254](https://github.com/BerriAI/litellm/pull/51254)). The stable
comparison floor is now **1.111.0** (see below). Prior
**[v1.109.0](https://github.com/BerriAI/litellm/releases/tag/v1.109.0)**
(2026-11-11) and earlier
[v1.109.0-rc.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-rc.1),
[v1.109.0-dev.2](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-dev.2),
and
[v1.109.0-dev.1](https://github.com/BerriAI/litellm/releases/tag/v1.109.0-dev.1)
builds are superseded. The live LTS patch on the prior line is
**[1.108.17](https://github.com/BerriAI/litellm/releases/tag/v1.108.17)**
(2026-11-24). Feature notes and daari's stance:

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
- **GPT-6.2 sampler / tools hygiene** — LiteLLM's GPT-6 family table strips
  `temperature` / `top_p` / `logprobs` and routes tools via Responses. daari's
  builtin `frontier.param_compat` does the same for `gpt-6.2-astra` /
  `gpt-6.2-sol` (effort `none` → `low`; chat+tools warn toward Responses)
  without a `drop_params` flag.
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

## LiteLLM 1.110.0 GA (history)

LiteLLM
**[v1.110.0](https://github.com/BerriAI/litellm/releases/tag/v1.110.0)**
(2026-11-18 01:36 UTC) shipped **stable** hours after this doc promoted
1.109.x, and was the comparison floor until 1.111.0 GA; the stable
comparison floor is now **1.111.0** (see below). The earlier
[v1.110.0-dev.1](https://github.com/BerriAI/litellm/releases/tag/v1.110.0-dev.1)
(2026-11-07; provider-reported `usage.cost`, tenant session affinity,
Lens-split Helm) is a **superseded** prerelease. 1.110.0 is LiteLLM's
largest architectural cut of the year; daari's stance, stated factually:

- **Rust-only router** — the Python router core is deleted
  ([#50178](https://github.com/BerriAI/litellm/pull/50178)); the Rust router
  core is the only router
  ([#49513](https://github.com/BerriAI/litellm/pull/49513)), with the Python
  host as its boundary, and a characterization suite guards the port
  ([#49610](https://github.com/BerriAI/litellm/pull/49610)). daari stays
  **pure-Python**, Apache 2.0, one `pip install`: no FFI boundary in the
  serving path, so the router is **pdb**-debuggable and patchable on-site.
  That is a packaging difference, not a performance claim either way.
- **SpendLogs ledger default** — the SpendLogs ledger is now the default
  accounting path and the accounting event tables are dropped
  ([#49872](https://github.com/BerriAI/litellm/pull/49872)). daari's analog
  is the on-box **SQLite** usage ledger (per-key / team / user / tier rows,
  `daari spend` exports) with Postgres as the optional control-plane store —
  no proxy-side schema migration to reach a ledger.
- **FIPS mode** — startup gate plus PBKDF2 UI hashes and KBKDF MCP keys
  ([#48600](https://github.com/BerriAI/litellm/pull/48600)). daari has **no
  FIPS gate**; this is a watch row, not a parity claim.
- **Agent Skills Hub** — portable skills API with submissions / review and
  security scans ([#50159](https://github.com/BerriAI/litellm/pull/50159)).
  Hosted hub surface; non-goal for daari (local `daari/skills` stay files on
  disk).
- **Model deprecation alerts** — `successor_model`, owner emails. daari's
  on-box twin is the lifecycle catalog (`models.lifecycle`, `migrate_to`,
  `daari_meta.warning=model_deprecated`, 410 `model_retired`; see the
  Opus 4.5 window below) — no SaaS email loop.
- **Experimental Redis / v2 caches removed**
  ([#50005](https://github.com/BerriAI/litellm/pull/50005)) — alongside the
  1.109 disk-backend removal, this reinforces that daari's $0 L0/L1
  **diskcache** path is a design choice LiteLLM no longer offers.

## LiteLLM 1.111.0 GA (stable comparison floor)

LiteLLM promoted
**[v1.111.0](https://github.com/BerriAI/litellm/releases/tag/v1.111.0)** to
**stable** on 2026-11-25; it is **GA** and the current **stable comparison
floor**. The live LTS patch is
**[1.108.17](https://github.com/BerriAI/litellm/releases/tag/v1.108.17)**
(2026-11-24; see the 1.108 LTS section). The earlier
[v1.111.0-rc.1](https://docs.litellm.ai/release_notes/v1.111.0rc1/v1-111-0-rc-1)
(2026-11-18) watch row is folded here — the GA promotion supersedes the
RC-watch posture. Feature set mapped to daari parity / non-goals:

- **Per-model TPM/RPM limit maps** on budgets and customers, enforced by the
  v3 limiter. daari parity predates the GA: per-key-per-model
  `rate_limit.models` (exact id, else longest prefix) with `model_rpm` /
  `model_tpm` defaults
  ([#1592](https://github.com/naveenreddyalka/daari/issues/1592)) and
  per-key-per-model UTC-day `model_rpd` / `model_tpd` with virtual-model
  failover past exhausted peers
  ([#2240](https://github.com/naveenreddyalka/daari/issues/2240)); rejects
  carry `X-RateLimit-Scope`. See
  [auth-and-keys](../guides/configuration/auth-and-keys.md#named-per-model-map).
- **Access groups via principal attribute rules** (SSO-attribute-driven
  RBAC). daari maps IdP claims to admin roles with `enterprise.sso` /
  `role_claim`, and SSO bearers are control-plane only — data-plane calls
  mint a virtual key (`POST /v1/daari/sso/session`) so budgets and model
  allowlists still bind per key. There is no attribute → model-access-group
  rule engine on-box; allowlists are per key / team. Honest gap, filed
  separately if a buyer asks.
- **Customer portal (beta)** UI plus **Customer Management** hierarchy;
  `/customer/new` and `/customer/update` reject unknown fields. daari has no
  customer portal and no customer object: end users are attributed via the
  OpenAI `user` field (or Anthropic `metadata.user_id`) with per-user
  `--user-rpd` / `--user-tpd` fences and per-user ledger rows. Hosted portal
  is a non-goal.
- **Native `/v1/messages` on the Rust path**; **refused-leg billing**;
  **transcription billed from provider-reported seconds**. daari serves
  `/v1/messages` natively in the same Python process (no bridge boundary),
  adds a discarded refused / `content_filter` L6 leg's `cost_usd` onto the
  serving attempt so the ledger reflects what was actually billed
  ([#2272](https://github.com/naveenreddyalka/daari/issues/2272); local
  refused legs stay $0), and prices ASR from upstream `usage` or audio
  **seconds**
  ([#2250](https://github.com/naveenreddyalka/daari/issues/2250)) — local
  Ollama / MLX ASR stays $0.
- **Retries may leave a pinned deployment**; **Claude Code subagent traffic
  kept off other agents' tier pins**. daari parity: session pins are scoped
  by conversation `prefix_hash`, so a subagent's tool-result turn cannot
  replay a parent loop's pin
  ([#2267](https://github.com/naveenreddyalka/daari/issues/2267)), and an
  open circuit, a down pinned model, or a tier cap beats the pin
  (`session_pin_override` logged) instead of retrying a dead pinned
  deployment.
- **Default performance alerts** (7-day latency / error spikes) and
  **dynamic rate limiter** with `rate_limited_by` on 429s. daari's on-box
  twin is Prometheus `/metrics` + the shipped Grafana panels and `daari
  doctor` tips (no SaaS alert email). Every gateway 429 (and concurrency
  503) also emits `rate_limited_by` / `X-Daari-Rate-Limited-By` with a
  stable enum (`key_rpm`, `team_tpm`, `model_rpd`, `mcp_server_rpm`,
  `concurrency`, `key_lockout`, `auth_throttled`, …) next to the existing
  `X-RateLimit-Scope` (`key` / `team` / `user` / `model` / `*_concurrency` /
  `mcp_server:<id>`) and `Retry-After` — LiteLLM parity for the limiter
  name, with Redis or SQLite counters rather than a cluster-wide dynamic
  limiter ([#2361](https://github.com/naveenreddyalka/daari/issues/2361)).
- **Gemini 4 Hydrogen** catalog and **Microsoft Web IQ `/v1/search`**.
  daari prices Gemini 4 ids from the on-box `pricing.models` ledger:
  Carbon / Argon intro windows via `effective_to`, and Hydrogen at the
  flat $1.50 / $7.50 list (cache read $0.075, Priority 1.8×, thinking
  level `xhigh`) — no hosted `model_prices` fetch required.
  `/v1/search` as a provider-backed search
  door is **N/A / watch**: daari's web-search path is the on-box
  escalate-to-search tool, not a Bing-shaped endpoint.
- **Non-root single image / `helm/litellm`**. daari's Docker image already
  runs as `USER daari`; Helm capacity notes live in
  [capacity-helm](../guides/operations/capacity-helm.md). No Lens / hosted
  Helm parity claimed.

### Anthropic API version `2026-10-21` sampling watch (#2384)

Anthropic API version **`2026-10-21`** removes `temperature` / `top_p` /
`top_k` for **every** model (not only Fable/Mythos). daari already strips that
trio when the client sends `anthropic-version: 2026-10-21`
(`apply_anthropic_version_sampling_compat`). Builtin `frontier.param_compat`
also strips the trio (plus effort / thinking / forced `tool_choice` hygiene)
for `claude-fable-5-1` / `claude-fable-5-2` / `claude-mythos-5-2` regardless
of version — LiteLLM's 1.110.2 / 1.111.0-rc.3 patch night
([litellm#52341](https://github.com/BerriAI/litellm/issues/52341)) special-cased
default `temperature=1` and let it through. **Watch:** if daari ever pins
default `anthropic-version` to `2026-10-21`, strip the sampling trio
unconditionally for all Anthropic ids (not only the Fable/Mythos table).

### Claude Opus 4.5 deprecation window (#2439)

Anthropic's Claude Platform release notes (2026-11-23) deprecate
`claude-opus-4-5` / `claude-opus-4-5-20251101` with API retirement on
**2027-01-22** and Claude Opus 5.5 as the migration target. daari ships the
window in the on-box lifecycle catalog (`_DEFAULT_MODEL_LIFECYCLE`,
operator `models.lifecycle` keys still win): `/v1/models` shows
`lifecycle=deprecated`, `shutdown_date` / `retires_at` `2027-01-22`, and
`migrate_to: claude-opus-5-5`; Chat / Messages / Responses keep serving with
`daari_meta.warning=model_deprecated` until the cutover, then default
`models.reject_retired` returns **410 `model_retired`**; `daari doctor`
`model_lifecycle` tips while any tier / frontier / pool slot still points at
4.5. `models.lifecycle_as_of: YYYY-MM-DD` rehearses the cutover before the
date. LiteLLM relies on its hosted `model_prices_and_context_window.json`
refresh plus the provider's own 404; there is no local deprecation calendar
or pre-cutover warning.

Measured on the same Ollama corpus: [benchmark vs LiteLLM](benchmark-vs-litellm.md). Short matrix: [compare](compare.md).
