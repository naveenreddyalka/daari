# OpenAI-Compatible SDK Setup

Use `daari` as a local OpenAI-compatible endpoint for Python or TypeScript SDK clients.

## Quick setup

```bash
daari setup openai-compat
```

This prints shell exports and writes `~/.daari/.env.example` with a safe local template.

## Required environment

```bash
export OPENAI_BASE_URL="http://127.0.0.1:11435/v1"
export OPENAI_API_KEY="daari-local"
export OPENAI_MODEL="daari"
```

Optional L6 frontier escalation key (not stored in `~/.daari/config.yaml`):

```bash
export DAARI_FRONTIER_API_KEY="sk-..."
```

You can also generate a profile/template hint with:

```bash
daari setup frontier-key --write-profile-snippet
```

## Python example

```python
from openai import OpenAI

client = OpenAI()  # Reads OPENAI_* env vars
response = client.chat.completions.create(
    model="daari",
    messages=[{"role": "user", "content": "Say hi in one sentence"}],
)
print(response.choices[0].message.content)
```

## TypeScript example

```typescript
import OpenAI from "openai";

const client = new OpenAI(); // Reads OPENAI_* env vars
const response = await client.chat.completions.create({
  model: "daari",
  messages: [{ role: "user", content: "Say hi in one sentence" }],
});
console.log(response.choices[0].message?.content);
```
