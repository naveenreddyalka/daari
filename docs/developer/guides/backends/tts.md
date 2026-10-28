# Local text-to-speech

**Outcome:** `POST /v1/audio/speech` stays on the machine. Point daari at **Ollama 0.40.9+ Phonon**, **Ollama 0.40.12+ `lfm3-audio`** (18-language ASR/TTS beside Phonon), Kokoro, openedai-speech, or any OpenAI-compatible TTS server.

## Config

`tts.base_url` is an OpenAI-compatible API root (it includes `/v1`), the same shape as `asr.base_url`. Point it at a local speech stack that already serves `POST /v1/audio/speech`. No TTS package is installed with daari.

```yaml
tts:
  base_url: http://127.0.0.1:11434/v1   # Ollama Phonon (0.40.9+); or Kokoro/openedai-speech
  model: ""    # optional; when set, replaces the client model
  voice: ""    # optional default when the request omits voice
  max_input_chars: 4096   # OpenAI-shaped cap; oversize input → 400 before guardrails/TTS
```

**Ollama Phonon (local-first):** as of Ollama **0.40.9**, the same daemon that serves chat tiers exposes streaming `POST /v1/audio/speech`. Ollama **0.40.11+** adds Phonon's Gradium **voice catalog** (`ollama show phonon` / `/api/show` `voices`) and **language tags**. Set `tts.base_url` to `{ollama.base_url}/v1` (for example `http://127.0.0.1:11434/v1`) and preferably `tts.model: phonon`. daari does not auto-wire this — `daari doctor` tips when TTS is empty and Ollama reports a speech-capable version; when Phonon is already configured it also tips if Ollama is older than **0.40.11** (catalog / language tags) or if `tts.model` is a 40M tag (license).

**Ollama `lfm3-audio` (beside Phonon):** Ollama **0.40.12+** can also list Liquid AI `lfm3-audio` for speech recognition, translation, and TTS in 18 languages (LFM Open License — not Phonon's CC BY-NC 40M cliff). Point the same `tts.base_url` at `{ollama.base_url}/v1` and set `tts.model: lfm3-audio`. Doctor tips when `/api/tags` lists `lfm3-audio` while TTS is empty, and notes the backend honestly when configured (no false Phonon license / Gradium voice-catalog tips).

**Pull recipe:**

```bash
ollama pull phonon                 # 31M English default — Apache-2.0
# Language / multilingual 40M checkpoints (Ollama 0.40.11+) — CC BY-NC 4.0:
ollama pull phonon:40m-fr
ollama pull phonon:40m-de
ollama pull phonon:40m-es
ollama pull phonon:40m-pt
ollama pull phonon:40m-multilingual
```

Then set `tts.model` to the pulled tag (for example `phonon:40m-fr`). The default `phonon` 31M weights stay **Apache-2.0**; the `phonon:40m-*` / `phonon:40m-multilingual` family is **CC BY-NC 4.0** (noncommercial) — procurement and doctor will surface that cliff.

**List voices:** `GET /v1/audio/voices` returns an OpenAI-shaped `{object, data:[{id,…}]}` catalog when `tts.base_url` is set. For Phonon, daari merges the upstream catalog with common OpenAI voice aliases (`alloy`, `echo`, …). On `POST /v1/audio/speech`, those OpenAI names map onto Phonon entries (for example `alloy` → `Zoey`); unknown voices return **400** with the available list. Streaming relay for chunked Phonon audio is unchanged.

**Phonon `response_format`:** Ollama Phonon accepts **`wav`** (default) and **`pcm`** only. Stock OpenAI clients often send `mp3`. When the TTS target is Phonon, daari coerces unsupported formats (including the gateway default `mp3`) to `wav`, and keeps `pcm` when the client asks for it. Non-Phonon OpenAI-compatible TTS backends keep the requested format unchanged.

Leave `base_url` empty and the route returns **501**. `daari doctor` stays quiet when Ollama is unreachable or older than 0.40.9. It warns when `tts.base_url` is set but `GET {base}/models` is unreachable.

Helm fleets can set `tts.baseUrl`. Optional chart values `tts.model` / `tts.voice` mount `DAARI_TTS__MODEL` / `DAARI_TTS__VOICE` so the pod always presents the on-box id (see [Capacity and Helm](../operations/capacity-helm.md)).

## Request

OpenAI JSON body: `model` (required unless `tts.model` is set), `input` (non-empty text, at most `tts.max_input_chars`, default **4096**), optional `voice` (falls back to `tts.voice`, then `alloy`), and `response_format` (for example `mp3`; Phonon targets are coerced to `wav` / `pcm` as above). Longer `input` returns **400** `invalid_request_error` naming the limit before guardrails or upstream. The JSON body itself is bounded by `server.max_body_bytes` (speech is carved out of the 100 MB `/v1/audio/` upload floor used by transcriptions). The response is raw audio bytes with a matching `Content-Type`. When the upstream uses chunked transfer (Ollama Phonon), daari **streams** those bytes to the client as they arrive; backends that send a fixed `Content-Length` stay fully buffered.

Auth, virtual-key request budgets, rate limits, model allowlists, and `X-Daari-Deadline-Ms` apply the same way as other gated routes. A key or team model allowlist is checked against the resolved model before any upstream call. Leave `base_url` empty and the route returns **501** without calling a cloud TTS API.

## Verify

```bash
curl -sS http://127.0.0.1:11435/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"tts-1","input":"hello from daari","voice":"alloy"}' \
  -o /tmp/daari-speech.mp3
```

With `tts.base_url` set, the file is non-empty audio. With nothing configured, the same call returns 501.

## Next

→ [Speech-to-text](asr.md) · [Capacity and Helm](../operations/capacity-helm.md) · [Chargeback](../observability/chargeback.md)
