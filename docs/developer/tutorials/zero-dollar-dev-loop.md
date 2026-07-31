# Tutorial: Zero-dollar local loop

**Outcome:** Answer repeatable prompts from $0 tiers (cache/tools/local) without L6.

## Steps

1. Install and `daari serve` with Ollama L3.
2. Set a project profile `no_frontier: true` or header `X-Daari-No-Frontier: true`.
3. Run the same curl twice — second is L0.
4. Optional: enable Lt for known safe commands via policy allowlist.
5. `daari report` — frontier_requests stays near zero.

## Verify

`daari_meta.tier` in {L0,L1,L2,Lt,L3,L4,L5}; never L6.

## Next

→ [Routing tiers](../concepts/routing-tiers.md)
