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
| PyPI package | `publish.yml` | GitHub release published (or manual dispatch, incl. TestPyPI) | Trusted publisher must be registered on PyPI — see below |
| Docker image | `docker.yml` | tag push → `ghcr.io/naveenreddyalka/daari:vX.Y.Z` + `latest` on main | ghcr package visibility (first publish creates it) |
| Docs site | `docs-site.yml` | push to main | GitHub Pages (auto-enabled) |

The build job runs `twine check --strict` on the sdist/wheel before any upload.

## Blocking one-time setup: PyPI trusted publisher

!!! danger "This is why v1.1.1, v1.1.2, and v1.2.0 never reached PyPI"
    The `build` job succeeded on all three releases; the `publish` job failed with
    `invalid-publisher: valid token, but no corresponding publisher`. The workflow
    is correct — PyPI simply has no publisher registered to trust it, and a failed
    publish does not fail the release, so it went unnoticed three times.

`scripts/release_pypi.py` drives everything around that one form:

```bash
python scripts/release_pypi.py check                    # what is blocking, changes nothing
python scripts/release_pypi.py publish --target testpypi # optional dry run
python scripts/release_pypi.py publish --target pypi      # triggers, watches, diagnoses
python scripts/release_pypi.py verify --version X.Y.Z     # clean-venv install check
```

`publish` reruns the failed job from the tag's own release run when one exists, so
the upload matches the tag instead of whatever `main` currently holds. It refuses
to publish a version already on the index, since PyPI uploads cannot be replaced,
and decodes an `invalid-publisher` failure back into the claim values to fix.

Because `daari` does not exist on PyPI yet, register a **pending** publisher at
[pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
using exactly these values — they must match the OIDC claims the workflow sends:

| Field | Value |
|-------|-------|
| PyPI Project Name | `daari` |
| Owner | `naveenreddyalka` |
| Repository name | `daari` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

No API token is created or stored. Then ship the already-tagged release without
re-tagging, by re-running just the failed job so it keeps the tag's ref:

```bash
gh run rerun $(gh run list --workflow publish.yml --limit 1 --json databaseId -q '.[0].databaseId') --failed
```

Dry-run against TestPyPI first if you prefer — it needs its own pending publisher
with environment `testpypi`:

```bash
gh workflow run publish.yml -f repository=testpypi
```

Verify: `pip install daari==X.Y.Z` in a clean venv, then `daari --help`.

## Homebrew formula

`Formula/daari.rb` needs the release tarball's sha256 plus a `resource` block for
every transitive dependency, because Homebrew builds with no network access and
`virtualenv_install_with_resources` installs only what the formula declares. Both
are generated — never hand-edited:

```bash
python scripts/update_formula.py --version X.Y.Z
```

The formula cannot be installed from a path — Homebrew 6 rejects formulae outside
a tap (`Error: Homebrew requires formulae to be in a tap`). It is served from
[naveenreddyalka/homebrew-daari](https://github.com/naveenreddyalka/homebrew-daari);
after regenerating, copy the file into that repo. Users additionally need
`brew trust naveenreddyalka/daari`, which Homebrew 6 requires for third-party taps.

To validate a change without touching the public tap, use a throwaway local tap —
`brew fetch` verifies every checksum without installing:

```bash
brew tap-new --no-git naveenreddyalka/formulatest
cp Formula/daari.rb "$(brew --repository naveenreddyalka/formulatest)/Formula/"
brew fetch --formula --build-from-source naveenreddyalka/formulatest/daari
brew untap naveenreddyalka/formulatest
```

## After release

- Verify `pip install daari==X.Y.Z` in a clean venv.
- Local deploy: the launchd watchdog redeploys `main` and runs live E2E within 2h.
- Update `CONTEXT.md` current-phase line and `docs/TRACKING.md`.
