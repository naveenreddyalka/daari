# Local speech-to-text

**Outcome:** `POST /v1/audio/transcriptions` and `POST /v1/audio/translations` stay on the machine. A cloud upload happens only when you opt in.

## Config

`asr.base_url` is an OpenAI-compatible API root (it includes `/v1`), the same shape as `frontier.base_url`. Point it at vLLM, whisper.cpp's OpenAI server, or any pool member that already serves `POST /v1/audio/transcriptions` and `POST /v1/audio/translations`. No Whisper or ffmpeg package is installed with daari.

```yaml
asr:
  base_url: http://127.0.0.1:8000/v1
  model: ""                  # optional; when set, replaces the client model
  frontier_fallback: false   # default — never upload audio implicitly
```

Leave `base_url` empty and the route returns **501**. `daari doctor` stays quiet in that case. It warns when `asr.base_url` is set but `GET {base}/models` is unreachable, and when `frontier_fallback` is true while frontier is disabled or no API key resolves. `frontier_fallback` stays off so existing installs do not start sending meetings to a hosted API. Set it to `true` only when `frontier.enabled` is true and a frontier key is configured; daari then forwards the transcription to eligible frontier slots in pool order (failover on transient failure). Virtual-key `no_frontier` blocks the upload (403); `region_pin` keeps audio on matching-region slots only (400 when none match).

Helm fleets can set `asr.baseUrl`, which mounts `DAARI_ASR__BASE_URL`. Optional chart value `asr.model` mounts `DAARI_ASR__MODEL` so the pod always presents the on-box whisper id. `asr.frontierFallback` defaults off and omits env; set it to true to mount `DAARI_ASR__FRONTIER_FALLBACK` so an empty base URL may forward one transcription to frontier (see [Capacity and Helm](../operations/capacity-helm.md)).

## Chat `input_audio` blocks

OpenAI chat completions and Responses message content may include
`{"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"|"mp3"}}`
parts. daari keeps those on the internal message and rebuilds them on the L6 OpenAI
payload so frontier never sees a silently stripped turn. When `asr.base_url` is set,
daari also POSTs each clip to the local ASR endpoint and appends the transcript to the
message text before local tiers run — voice-agent turns can stay on-box. With ASR unset,
local tiers see only the text caption (if any); the raw audio still rides to frontier on
escalation.

## Request

OpenAI multipart form: `file`, `model` (required unless `asr.model` is set), optional `language` (transcriptions only), `prompt`, and `response_format=json`. Translations omit `language` and forward to `{base}/audio/translations`. The JSON body includes `text`. Leave `base_url` empty and either route returns **501** without uploading. `response_format` other than `json` is **400**.

Auth, virtual-key request budgets, and rate limits apply the same way as chat completions. A key or team model allowlist is checked against the resolved model (`asr.model` when set, otherwise the form `model`) and returns 403 `model_not_allowed` before any upstream call. Unset allowlists stay unrestricted. A successful transcription counts as one request.

## Verify

With `asr.base_url` set, a short clip returns `{ "text": "..." }`. With nothing configured, the same call returns 501 and the file is not uploaded.

## Next

→ [vLLM / llama.cpp](../configuration/vllm-local-tier.md) · [Ollama](ollama.md) · [Capacity and Helm](../operations/capacity-helm.md)
