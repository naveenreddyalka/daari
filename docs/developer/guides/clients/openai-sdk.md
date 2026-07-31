# OpenAI-compatible SDK

**Outcome:** Python/TS OpenAI clients talk to daari.

## Steps

```bash
daari setup openai-compat
```

```bash
export OPENAI_BASE_URL="http://127.0.0.1:11435/v1"
export OPENAI_API_KEY="daari-local"   # or server.api_key / virtual key
export OPENAI_MODEL="daari"
```

Optional L6 key (env only, never stored in config.yaml):

```bash
export DAARI_FRONTIER_API_KEY="sk-..."
```

## Python

```python
from openai import OpenAI
client = OpenAI()
print(client.chat.completions.create(
    model="daari",
    messages=[{"role": "user", "content": "Say hi"}],
).choices[0].message.content)
```

## Verify

Second identical request should show L0 when you pass `X-Daari-Meta: true` via your HTTP client / `extra_headers`.

## Next

→ [Headers](../../reference/headers.md) · [Quickstart](../../get-started/quickstart.md)
