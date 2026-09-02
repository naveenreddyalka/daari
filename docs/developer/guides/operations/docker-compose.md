# Docker Compose

**Outcome:** Run daari + Ollama with one command.

## Steps

```bash
docker compose up
```

Profiles:

```bash
docker compose --profile org up              # org-cache :11436
docker compose --profile backends up -d      # Redis + Postgres
./scripts/smoke_backends.sh                  # SKIP if no Docker daemon
```

## Verify

`curl -fsS http://127.0.0.1:11435/ready`

## Supply chain: verify the image

Images pushed to ghcr from `main` and `v*` tags are signed with cosign
(keyless, GitHub OIDC) and carry an SBOM plus a SLSA provenance attestation
(issue #295). Before running a pulled image:

```bash
cosign verify ghcr.io/naveenreddyalka/daari:latest \
  --certificate-identity-regexp 'https://github.com/naveenreddyalka/daari' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

The identity is the repository's GitHub Actions workflow; any other signer
must fail verification. Inspect the attached SBOM and provenance:

```bash
docker buildx imagetools inspect ghcr.io/naveenreddyalka/daari:latest \
  --format '{{ json .SBOM }}'
docker buildx imagetools inspect ghcr.io/naveenreddyalka/daari:latest \
  --format '{{ json .Provenance }}'
```

## Next

→ [Capacity and Helm](capacity-helm.md) · [Install](../../get-started/install.md)
