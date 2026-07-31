# Demo script

Aligned with [Quickstart](../developer/get-started/quickstart.md) and [Pitch outline](../developer/resources/pitch-outline.md).

## Setup (once)

```bash
git clone https://github.com/naveenreddyalka/daari.git && cd daari
docker compose up
# wait until GET http://127.0.0.1:11435/ready succeeds
```

Or from source: `./scripts/demo.sh`.

## Narrative (5–7 minutes)

1. **Problem (30s)** — Agents and in-app chat send everything to frontier APIs; repeatable work and off-topic chat burn money.
2. **Show daemon (30s)** — `curl /health` and `/ready`.
3. **First completion (1m)** — Chat completion with `X-Daari-Meta: true`; point at `daari_meta.tier` (local).
4. **Cache win (1m)** — Identical request → `tier: L0`, `cache_hit: true`.
5. **Savings (1m)** — `daari report` or web UI (`daari web-ui serve`).
6. **Boundaries (1–2m)** — Enable fintech example topics; out-of-scope prompt → `tier: boundary` with zero model call (`python scripts/smoke_boundaries.py`).
7. **Client (optional)** — Claude Code localhost or Cursor tunnel slide.
8. **Close** — Local-first path: cache → tools → local → frontier last; open source; star/try Compose.

## Backup slides / talking points

- Not a multi-cloud proxy — an execution router you own.
- Cache trust is measurable (false-hit / diversity).
- Enterprise: Redis/Postgres, Helm, org cache, SSO/virtual keys.
