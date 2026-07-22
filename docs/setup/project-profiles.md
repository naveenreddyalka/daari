# Per-project profiles (`.daari.yaml`)

Different repos want different routing. A docs repo can cap at the small local
model; a sensitive repo can forbid frontier escalation entirely; a
latency-critical repo can set a response budget. Profiles let you commit those
defaults next to the code (issue #91, roadmap Phase C1).

## Create a profile

```bash
daari project init /path/to/repo     # writes a commented .daari.yaml template
daari project show /path/to/repo     # what daari would apply for that path
```

Supported keys (anything else is ignored — a malformed file never breaks a
request):

```yaml
routing:
  max_tier_for_chat: L3    # highest local tier (L3 | L4 | L5)
  no_frontier: true        # never escalate to L6 for this repo
  latency_budget_ms: 3000  # max acceptable local-model latency
client_id: my-repo         # attribution in `daari report`
```

## How clients opt in

The daemon can't guess which repo a request belongs to, so clients declare it
with a header pointing anywhere inside the repo:

```
X-Daari-Project: /Users/you/code/my-repo
```

daari walks up from that path to find `.daari.yaml`, caches the parsed profile
by mtime, and applies it as request defaults. **Explicit per-request headers
always win** — `X-Daari-Tier-Cap`, `X-Daari-Latency-Budget`,
`X-Daari-Client-Id`, and `X-Daari-Tier-Override` all take precedence over the
profile.

Per client:

- **Claude Code** — add to the repo's `.claude/settings.json` (or your global
  one) so every request carries the header:

  ```json
  {
    "env": {
      "ANTHROPIC_CUSTOM_HEADERS": "X-Daari-Project: /Users/you/code/my-repo"
    }
  }
  ```

- **SDKs / scripts** — pass `extra_headers={"X-Daari-Project": "/path/to/repo"}`
  (OpenAI SDK) or `default_headers` (Anthropic SDK).
- **curl** — `-H "X-Daari-Project: $PWD"`.
- **Cursor** — cannot send custom headers through BYOK; use the global
  `routing.max_tier_for_chat` in `~/.daari/config.yaml` instead.

## Precedence order

1. `X-Daari-Tier-Override` (exact tier, beats everything)
2. Explicit request headers (`X-Daari-Tier-Cap`, `X-Daari-Latency-Budget`, …)
3. `.daari.yaml` project profile
4. Global `~/.daari/config.yaml`

Note: `no_frontier: true` in a profile is a hard opt-out — it applies even if
the header is absent, since it is a safety preference rather than a tuning
knob.
