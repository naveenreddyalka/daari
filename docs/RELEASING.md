# Releasing daari

Human-gated by design — agents prepare, a maintainer pulls the trigger.

## Checklist

1. Bump `version` in `pyproject.toml`; move `CHANGELOG.md` Unreleased → new section.
2. Write `docs/RELEASE-vX.Y.Z.md` (scope, highlights, validation results).
3. Merge via PR (4 CI checks). Then tag + GitHub release:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z — <name>" --notes-file docs/RELEASE-vX.Y.Z.md
   ```

## What automation does from there

| Artifact | Workflow | Trigger | Gate |
|----------|----------|---------|------|
| PyPI package | `publish.yml` | GitHub release published (or manual dispatch, incl. TestPyPI) | **One-time setup:** create the `daari` project on PyPI and add this repo as a [trusted publisher](https://docs.pypi.org/trusted-publishers/) for the `pypi` environment (no token stored). Until then the publish job fails harmlessly |
| Docker image | `docker.yml` | tag push → `ghcr.io/naveenreddyalka/daari:vX.Y.Z` + `latest` on main | ghcr package visibility (first publish creates it) |
| Docs site | `docs-site.yml` | push to main | GitHub Pages (auto-enabled) |

The build job runs `twine check` on the sdist/wheel before any upload.

## After release

- Verify `pip install daari==X.Y.Z` in a clean venv (once PyPI publishing is configured).
- Local deploy: the launchd watchdog redeploys `main` and runs live E2E within 2h.
- Update `CONTEXT.md` current-phase line and `docs/TRACKING.md`.
