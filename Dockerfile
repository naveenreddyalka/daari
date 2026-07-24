# daari — local-first LLM router (issue #105)
# Build:  docker build -t daari .
# Run:    docker run -p 11435:11435 -e DAARI_OLLAMA__BASE_URL=http://host.docker.internal:11434 daari
# Better: docker compose up (bundles Ollama; see docker-compose.yml)

FROM python:3.12-slim AS build

WORKDIR /src
COPY pyproject.toml README.md ./
COPY daari ./daari
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim

# curl is used by the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 daari

COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# All state (config, caches, ledger, traces) lives under ~/.daari — mount it
# to persist across container restarts. Pre-create it owned by the app user
# so named volumes inherit the right ownership.
RUN mkdir -p /home/daari/.daari && chown -R daari:daari /home/daari/.daari
USER daari
VOLUME ["/home/daari/.daari"]

# Docker does not derive HOME from USER — set it or ~/.daari resolves to /.daari.
ENV HOME=/home/daari \
    DAARI_SERVER__HOST=0.0.0.0 \
    DAARI_OLLAMA__BASE_URL=http://ollama:11434

EXPOSE 11435

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:11435/health || exit 1

CMD ["daari", "serve", "--host", "0.0.0.0", "--port", "11435"]
