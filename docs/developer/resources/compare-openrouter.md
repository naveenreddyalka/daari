# daari vs OpenRouter

OpenRouter is a **hosted marketplace** (400+ models, one key, price/latency routing). daari is an **on-device router**. We do not clone the catalog. L6 can point at OpenRouter when you actually want the cloud.

| | OpenRouter | daari |
|--|------------|-------|
| Where it runs | Their API | Your localhost (or your cluster) |
| Default inference | Remote, billed | On-device $0 tiers first |
| Model choice | Marketplace + provider object | Task-aware local tiers, then one L6 slot |
| Privacy | Prompts leave the machine | Stay local until L6 |
| License | Hosted product | Apache 2.0 |

**Pick OpenRouter** when you want one key and many remote models.

**Pick daari** when the goal is *not sending* most Cursor / Claude Code turns to any remote model.

## Rebuilt default provider routing (2026-10-28)

OpenRouter's [rebuilt default provider routing](https://openrouter.ai/blog/announcements/how-we-rebuilt-provider-routing/)
(28 Oct 2026) live-scores cloud endpoints on **realized price, TTFT,
throughput, and error rate**. Their published deltas: **−16.9% median TTFT**,
**−46% capacity 429s**, and about **6% lower cost**. Caller soft-reorder knobs
`preferred_min_throughput` / `preferred_max_latency` (percentile-aware) are
documented on OpenRouter's
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
page — they bias the marketplace pick without hard-failing when no endpoint
meets the threshold.

**daari stance (local-first):** that marketplace optimizer is not a clone
target. What ships on-box:

- **Ordered** `routing.virtual_models` failover — list order is the default
  candidate walk (breaker-open hops skipped).
- **Performance-aware** selection — opt-in
  `routing.virtual_model_selection: performance` reorders candidates by
  in-process EWMA of latency and error rate across local tiers and estate
  OpenAI-compatible backends (#2052). No catalog telemetry leaves the machine.
- **Cost-aware** selection — opt-in
  `routing.virtual_model_selection: cost` orders by blended $/1M from the
  in-tree pricing table (3:1 input:output); local/unpriced candidates sort as
  0 so local-first falls out of the arithmetic (#2164).

daari does **not** claim OpenRouter Private Endpoints or CSAM in-flight
screening parity here — those trust boundaries stay in the sections below
(#2038). Soft throughput/latency *caller* knobs like OpenRouter's
`preferred_*` thresholds are a marketplace feature; daari's counter is the
virtual-model selection modes above, not a hosted percentile router.

## Auto Router and Auto Code (2026-11-06)

OpenRouter's rebuilt
[Auto Router](https://openrouter.ai/blog/announcements/auto-and-auto-code-routers/)
(`openrouter/auto`) and **Auto Code** (`openrouter/auto-code`) (6 Nov 2026)
weigh ~eleven live factors per request (pricing, provider health, benchmarks,
cache state) and pick a **model and reasoning effort** from the
governance-allowed cloud pool. That is a hosted marketplace router: prompts
still leave the machine.

daari does **not** clone the hosted Auto / Auto Code marketplace. The
local-first counterpart on-box is:

- `routing.virtual_models` with selection modes (`ordered` /
  `performance` / `cost`) so candidate walk stays on-device.
- `routing.signal_overrides` levers (category / `max_tier` / `tier_pin` /
  `reasoning_effort` when configured) for governance without a cloud pool.
- Optional `routing.virtual_model_latency_slo_ms` demotion so over-SLO peers
  lose priority before cost or performance reorder.

Operators who still want cloud may point the single L6 slot at
`openrouter/auto` or `openrouter/auto-code`; local tiers remain the default
path, and budgets / audit stay on the same box.

## Private Endpoints vs local tiers

OpenRouter [Private Endpoints](https://openrouter.ai/blog/announcements/private-endpoints/)
(late Oct 2026) let Enterprise BYOK dedicated or fine-tuned deployments show up
as catalog slugs with org-private visibility — still reached through the same
OpenRouter API. That is a private *deployment* on a shared request path, not an
on-device hop.

| | OpenRouter Private Endpoints | daari |
|--|------------------------------|-------|
| Where weights run | Your dedicated/fine-tuned cloud deploy | Local L3–L5 (Ollama / pool) |
| Who is on the request path | OpenRouter + the endpoint host | Your process (and optional one L6 slot) |
| Catalog | Org-private slug via OpenRouter | Configured tier map / virtual models |
| When it helps | Enterprise wants one OpenRouter key + private deploys | Air-gapped or “most turns never leave the box” |

daari’s single L6 slot can still point at OpenRouter (including a private slug)
when you *choose* cloud; local tiers stay the default.

## CSAM in-flight screening vs on-box guardrails

OpenRouter’s [CSAM screening](https://openrouter.ai/blog/announcements/csam-screening/)
runs in-flight across inference, including Zero Data Retention (ZDR) traffic.
Flagged content may be retained for human review or legal preservation — so
“ZDR” here means provider retention policy for ordinary traffic, not a guarantee
that no bytes are ever kept after a safety flag.

daari decision guardrails and local tiers run on-box: prompts do not leave the
estate unless you escalate to L6. That is a different trust boundary (your host
and your policy), not a claim that local software replaces provider legal
obligations on cloud hops.

When a virtual key or team sets `region_pin` to `us` or `eu` and L6 is an
OpenRouter slot, daari rewrites the request to
`https://us.openrouter.ai/api/v1` or `https://eu.openrouter.ai/api/v1` (OpenRouter
in-region routing) instead of the global host. Non-OpenRouter slots still match
on the slot's configured `region` label only.

Stripe announced an OpenRouter acquisition (Aug 2026). That does not change daari’s job. Roadmap: [ROADMAP-v3](../../prd/ROADMAP-v3.md). Short matrix: [compare](compare.md).
