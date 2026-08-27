# daari vs OpenRouter

OpenRouter is a **hosted marketplace** (400+ models, one key, price/latency routing). daari is an **on-device router**. We do not clone the catalog. L6 can point at OpenRouter when you actually want the cloud.

| | OpenRouter | daari |
|--|------------|-------|
| Where it runs | Their API | Your localhost (or your cluster) |
| Default inference | Remote, billed | On-device $0 tiers first |
| Model choice | Marketplace + provider object | Task-aware local tiers, then one L6 slot |
| Privacy | Prompts leave the machine | Stay local until L6 |
| License | Hosted product | PolyForm Noncommercial (source-available) |

**Pick OpenRouter** when you want one key and many remote models.

**Pick daari** when the goal is *not sending* most Cursor / Claude Code turns to any remote model.

Stripe announced an OpenRouter acquisition (Aug 2026). That does not change daari’s job. Roadmap: [ROADMAP-v3](../../prd/ROADMAP-v3.md). Short matrix: [compare](compare.md).
