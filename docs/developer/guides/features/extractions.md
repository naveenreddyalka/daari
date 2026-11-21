# Extractions (`POST /v1/extractions`)

OpenRouter Extractions twin on daari: typed fields (`text`, `number`, `date`,
`list`, `estimate`, `forecast`, …) from `state` and optional `assets`.

## Request

```json
{
  "model": "d1",
  "state": "Invoice INV-2291. Total $1080.",
  "fields": {
    "invoice_number": { "type": "text" },
    "total": { "type": "number", "decimals": 2, "unit": "USD" }
  },
  "reference_date": "2026-10-28"
}
```

Unknown top-level keys (including Decisions `questions`) and unknown field
types return **400**.

## Routing

| Model | Path |
|-------|------|
| Local decisions catalog (`d1`, `nimble`, …) | systemone `/v1/extractions` — `daari_meta.tier=local`, `cost_usd=0` |
| Frontier extraction slug (`cloudflare/clairic`, …) | L6; OpenRouter slots use `/api/alpha/extractions` |

See [http-api.md](../../reference/http-api.md#extractions).
