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
