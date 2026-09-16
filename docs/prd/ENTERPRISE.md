# daari — Enterprise gap scan (living PRD)

> Maintained by the daily **prd-cycle** automation ([docs/automations/prd-cycle.md](../automations/prd-cycle.md)).
> Mandate: fastest credible path to a production-grade router enterprises run
> instead of LiteLLM, Portkey, Kong AI Gateway, or a cloud gateway — and keep
> the `auto-dev` backlog fed with the next most valuable work.
> Scoring: impact 1–5 (adoption/retention weight), effort 1–5 (subsystems touched,
> invasiveness). Priority label = impact − effort (≥3 → P1, 1–2 → P2, ≤0 → P3).
> Keep under ~300 lines; prune rows that ship or go stale.
> Phase-E org cache/learning spec: [phase-e-enterprise.md](phase-e-enterprise.md).

---

## Where daari stands (verified in-tree, 2026-09-16)

**Late-15 leftovers all shipped** (profile pins, doctor audit/webhook,
Responses retention, request-quota soft band, L0 singleflight). Mid-session
drain emptied the backlog again; this refill keeps the loop fed.

**Positioning:** LiteLLM stable **v1.100.1** (2026-09-10) is maintenance on
v1.100.0 (access-group budgets, custom auto-router tiers, MCP introspection,
model hub). v1.101 / v1.102 remain RC for `/v1/responses/input_tokens` and
routing offensive. Portkey / Kong / OpenRouter / Ollama / MCP SEP-1933: flat.

**Inward theme:** close stream-path cache stampede leftover; open Responses
token-count parity; start TTFT observability; facade-wide soft quota warn;
doctor HA footgun for disk L0 under replicas.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Stream path skips L0 singleflight** — #499 covered non-stream only | 3 | 2 | GPTCache / LiteLLM | Same in-process map; Cursor streams by default | **Filed** (P2) |
| 2 | **`POST /v1/responses/input_tokens`** — LiteLLM stable parity | 2 | 2 | LiteLLM | Local estimate / Anthropic count; $0 | **Filed** (P2) |
| 3 | **No Prometheus TTFT histogram** — blocks percentile-TTFT routing | 2 | 2 | LiteLLM | Instrument local stream first-byte | **Filed** (P2) |
| 4 | **Request-quota soft warn OpenAI-only** — Anthropic/Responses miss `daari_meta` | 3 | 1 | — | One soft signal across facades | **Filed** (P2) |
| 5 | **Doctor quiet on multi-replica disk L0** — fleet still stamps per pod | 2 | 1 | — | Warn when replicas>1 without Redis cache | **Filed** (P3) |
| 6 | **Percentile-TTFT routing** | 2 | 3 | LiteLLM | Needs TTFT histograms first | Watch |
| 7 | **WIF upstream provider auth** | 3 | 3 | Portkey | `secret://oauth` covers most | Watch |
| 8 | **MCP agent identity (SEP-1933)** | 3 | 3 | MCP Tier-1 SDKs | Draft | Watch |
| 9 | **SOC 2 / Gemini facade / A2A / admin UI / images / realtime** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: late-15 filed rows (all shipped 2026-09-16 morning).

Open backlog after this run: four P2 + one P3 from the 2026-09-16 refill.

---

## Path to enterprise-grade — next 5 milestones

1. **Stream L0 singleflight** — Cursor-class clients stop stampeding on stream.
2. **Responses input_tokens** — count without a full round-trip.
3. **TTFT metrics** — foundation for percentile local routing.
4. **Facade-wide soft quotas** — Anthropic/Responses match OpenAI soft warn.
5. **Honest multi-replica doctor** — disk L0 under replicas is a loud warn.

---

## Changelog

- **2026-09-16** — Late-15 leftovers shipped (PRs #501–#505). Backlog empty;
  refilled five issues (stream singleflight, Responses input_tokens, TTFT
  histogram, facade soft quota, doctor multi-replica Redis). Outward: LiteLLM
  v1.100.1 noted; v1.101/102 still RC. Portkey/Kong/OpenRouter flat.
- **2026-09-15 (late)** — Same-day fleet sprint closed (#481–#485 → PRs
  #490–#494; #476–#478 earlier). Backlog empty mid-session; refilled five P2
  leftovers (profile pins, doctor audit/webhook warnings, Responses
  retention, request-quota soft band, L0 singleflight). Outward: LiteLLM
  v1.100.0 (access-group budgets, custom router tiers) noted; v1.101 bar
  unchanged. Portkey/Kong/OpenRouter/Ollama flat.
- **2026-09-15** — Fifth same-day drain: #463–#467 merged overnight (PRs
  #469–#473). Never-empty refill + scheduled Actions `prd-cycle` (PR #479)
  and session cost rollup (PR #480). Filed #481–#485 (fleet half-finished).
- **2026-09-14** — Redis resilience audit; filed #463–#467; all shipped
  overnight.
- **2026-09-13→08-28** (condensed) — tenancy, batches, Kong parity, labeler,
  Apache 2.0, this PRD.
