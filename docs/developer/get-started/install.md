# Install

**Outcome:** daari CLI available and ready to `daari serve`.

## Option A — Docker Compose (recommended)

Bundles Ollama + model pull + daari:

```bash
git clone https://github.com/naveenreddyalka/daari.git
cd daari
docker compose up
```

Daemon: `http://127.0.0.1:11435`. Readiness: `GET /ready`. Image: `ghcr.io/naveenreddyalka/daari`.

Optional profiles:

```bash
docker compose --profile org up          # org-cache on :11436
docker compose --profile backends up -d  # Redis + Postgres
```

## Option B — from source

```bash
git clone https://github.com/naveenreddyalka/daari.git && cd daari
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional extras: pip install -e ".[redis,postgres,oidc,otel]"
ollama pull llama3.2:3b
daari serve
```

## Option C — Homebrew (macOS/Linux)

```bash
brew tap naveenreddyalka/daari
brew trust naveenreddyalka/daari
brew install daari
ollama pull llama3.2:3b
daari serve
```

`brew trust` is not optional — Homebrew 6 refuses to load formulae from
third-party taps until you trust them explicitly. The formula compiles the Rust
extensions in `pydantic-core` and `watchfiles`, so the first install pulls the
Rust toolchain and takes a few minutes.

Tap: [naveenreddyalka/homebrew-daari](https://github.com/naveenreddyalka/homebrew-daari).

## Option D — pip

!!! warning "Not published yet"
    `pip install daari` fails; nothing is on PyPI. Tracked in
    [#160](https://github.com/naveenreddyalka/daari/issues/160), which needs a
    one-time trusted-publisher registration. Use Option A, B, or C.

## Verify

```bash
curl -fsS http://127.0.0.1:11435/health
curl -fsS http://127.0.0.1:11435/ready
daari doctor
```

## Next

→ [Quickstart](quickstart.md) · [First client](first-client.md)
