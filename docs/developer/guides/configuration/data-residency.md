# Data residency

**Outcome:** Keep L0–L5 on your hardware and pin L6 fallback to a declared
region so residency review has evidence, not hope.

Most daari traffic never leaves the box: L0/L1 cache, rules, and local L3–L5
tiers run on the operator's GPUs. Only L6 frontier escalation crosses a
boundary. Region pins restrict which L6 slots are eligible — the same fail-closed
pattern as [`provider.zdr`](budgets-frontier.md#providers--fallback).

## Slot declaration

Each frontier provider may declare a free-form `region` label (`us`, `eu`,
`au`, `in`, `jp`, …):

```yaml
frontier:
  enabled: true
  providers:
    - id: openrouter-us
      base_url: https://us.openrouter.ai/api/v1
      model: openrouter/auto
      api_key_env: OPENROUTER_API_KEY
      region: us
      zdr: true
    - id: openrouter-eu
      base_url: https://eu.openrouter.ai/api/v1
      model: openrouter/auto
      api_key_env: OPENROUTER_API_KEY
      region: eu
    - id: openai-au
      base_url: https://au.api.openai.com/v1
      model: gpt-6-luna
      api_key_env: OPENAI_API_KEY
      region: au
    - id: openai-in
      base_url: https://in.api.openai.com/v1
      model: gpt-6-luna
      api_key_env: OPENAI_API_KEY
      region: in
    - id: openai-jp
      base_url: https://jp.api.openai.com/v1
      model: gpt-6-luna
      api_key_env: OPENAI_API_KEY
      region: jp
```

OpenRouter's [US / EU in-region routing](https://openrouter.ai/blog/announcements/us-in-region-routing/)
endpoints decrypt and serve entirely in-region on Business/Enterprise plans.
OpenAI's AU / IN / JP data-residency hosts (`au.api.openai.com`,
`in.api.openai.com`, `jp.api.openai.com`) store in-region; processing for those
regions may still leave the region — pin them only when that honesty matches
your review. daari never silently routes a pinned request to an unlabeled or
mismatched slot.

## Key / team pin

```bash
daari keys create compliance --region-pin eu
daari keys team-create eu-team --region-pin eu
```

Pinned keys (or keys on a pinned team) only consider L6 slots whose `region`
matches (case-insensitive). Local tiers are unaffected. When escalation needs
L6 and no matching slot exists, daari keeps the best local answer
(`warning: region_pin_unavailable`) rather than leaving the region; paths that
cannot soft-fail return HTTP 400 naming the pin.

## Evidence

L6 responses that used a regional slot set `daari_meta.region` and the
`x-daari-region` response header so logs and SIEM pipelines can prove residency
per request.

Pinned `us`/`eu`/`au`/`in`/`jp` traffic on OpenAI models released on or after
2026-03-05 also bills at **1.10×** the standard (or Fast/Ultrafast) rate so
`cost_usd` matches the regional invoice (see
[budgets and frontier](budgets-frontier.md#service-tier-pricing)).

## Next

→ [Budgets and frontier](budgets-frontier.md) · [Auth and keys](auth-and-keys.md)
