# Learning loop

**Outcome:** Understand the opt-in path from outcomes to better local routing (and optional fine-tunes).

## Flow

1. **Capture** — implicit outcomes + optional accept/reject feedback
2. **Tune** — per-category confidence thresholds (`daari learn recommend`)
3. **Examples** — opt-in capture for datasets
4. **Fine-tune** — MLX LoRA (`daari learn finetune`) → `daari learn deploy`
5. **Collective** — anonymized stats export only (`daari learn export-stats`); never prompts
6. **Propose defaults** — `daari learn propose-defaults` writes YAML proposals (never auto-promotes)

## Principles

- On-device by default
- Review-gated promotion
- Metadata-only for any shared export

## Next

→ [Config overview](../guides/configuration/overview.md) · PRD deep-dive (internal): `docs/prd/learning.md`
