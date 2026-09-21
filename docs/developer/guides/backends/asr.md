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

Leave `base_url` empty and the route returns **501**. `daari doctor` stays quiet in that case. It warns when `asr.base_url` is set but `GET {base}/models` is unreachable, and when `frontier_fallback` is true while frontier is disabled or no API key resolves. `frontier_fallback` stays off so existing installs do not start sending meetings to a hosted API. Set it to `true` only when `frontier.enabled` is true and a frontier key is configured; daari then forwards one request to that frontier base (the first provider in `frontier.providers`, otherwise `frontier.base_url`).

Helm fleets can set `asr.baseUrl`, which mounts `DAARI_ASR__BASE_URL` (see [Capacity and Helm](../operations/capacity-helm.md)).

## Request

OpenAI multipart form: `file`, `model` (required unless `asr.model` is set), optional `language` (transcriptions only), `prompt`, and `response_format=json`. Translations omit `language` and forward to `{base}/audio/translations`. The JSON body includes `text`. Leave `base_url` empty and either route returns **501** without uploading. `response_format` other than `json` is **400**.

Auth, virtual-key request budgets, and rate limits apply the same way as chat completions. A key or team model allowlist is checked against the resolved model (`asr.model` when set, otherwise the form `model`) and returns 403 `model_not_allowed` before any upstream call. Unset allowlists stay unrestricted. A successful transcription counts as one request.

## Verify

With `asr.base_url` set, a short clip returns `{ "text": "..." }`. With nothing configured, the same call returns 501 and the file is not uploaded.

## Next

→ [vLLM / llama.cpp](../configuration/vllm-local-tier.md) · [Ollama](ollama.md)
