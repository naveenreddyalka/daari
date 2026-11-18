# Tutorial: Coding router (Auto Code twin)

**Outcome:** Point coding-agent traffic at a local-first virtual model that
walks cheap local candidates before one L6 slot, raises reasoning effort on
code signals, and optionally demotes over-SLO peers — without cloning
OpenRouter's hosted Auto Code marketplace.

## Steps

1. Confirm Ollama (or another local tier) is reachable and `daari serve` is up.
2. Paste the snippet below into `~/.daari/config.yaml` (merge under existing
   `routing:` if you already have one). Swap `L4` / the frontier id for models
   you actually run.
3. Restart or live-PATCH routing ownership if the config editor is on.
4. Point the IDE / agent at virtual model name `coding` (or rename the map key).
5. Optional: `daari doctor` — if you set a code-category `signal_overrides` rule
   without any `virtual_models`, doctor tips that the compose is incomplete.

```yaml
routing:
  virtual_models:
    coding:
      - L4
      - openai/gpt-4o-mini
  virtual_model_selection: cost
  signal_overrides:
    - id: code-effort
      match:
        category: code_gen
      reasoning_effort: high
  virtual_model_latency_slo_ms:
    coding: 1200
```

- `virtual_model_selection: cost` keeps $0 local candidates ahead of priced L6
  peers (local sorts as 0).
- The `code_gen` match raises `reasoning_effort` only when the client omitted it.
- `virtual_model_latency_slo_ms.coding` is optional; drop it if you do not want
  SLO demotion under `cost` / `performance` selection.

## Verify

- Requests with `model: coding` record `daari_meta.virtual_model` and a
  `virtual_candidate`.
- Code-shaped prompts get the override effort when the client left effort unset.
- `daari doctor` stays quiet on `coding_router_compose` once `virtual_models`
  is non-empty.

## Next

→ [Routing tiers — named virtual models](../concepts/routing-tiers.md#named-virtual-models)
· [OpenRouter compare (Auto Code)](../resources/compare-openrouter.md)
