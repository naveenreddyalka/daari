"""Fill the Homebrew formula's release hash and Python resource blocks (issue #160).

The formula cannot be maintained by hand. It needs the sha256 of the release
tarball, which only exists once a tag is pushed, plus a `resource` block for
every transitive runtime dependency, because Homebrew builds without network
access and `virtualenv_install_with_resources` installs only what is declared.

Usage:
    python scripts/update_formula.py --version 1.2.0            # tarball hash + resources
    python scripts/update_formula.py --version 1.2.0 --check    # verify, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMULA_PATH = REPO_ROOT / "Formula" / "daari.rb"
TARBALL_URL = "https://github.com/naveenreddyalka/daari/archive/refs/tags/v{version}.tar.gz"
PYPI_URL = "https://pypi.org/pypi/{name}/{version}/json"
PLACEHOLDER_SHA = "0" * 64

# Homebrew provides these itself, so they must not become resources.
EXCLUDED = {"daari", "pip", "setuptools", "wheel"}


class ReleaseError(RuntimeError):
    """A step that must stop the release rather than publish something broken."""


def sha256_of_url(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            digest = hashlib.sha256()
            for chunk in iter(lambda: response.read(1 << 16), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ReleaseError(
                f"{url} does not exist yet — push the tag and let the release "
                "publish before filling the formula."
            ) from exc
        raise ReleaseError(f"fetching {url} failed: {exc}") from exc


def resolve_runtime_dependencies() -> dict[str, str]:
    """Resolve the runtime dependency set to exact versions, without dev extras."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--ignore-installed",
                "--quiet",
                "--report",
                str(report),
                str(REPO_ROOT),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ReleaseError(f"dependency resolution failed:\n{result.stderr}")
        data = json.loads(report.read_text(encoding="utf-8"))

    resolved: dict[str, str] = {}
    for item in data.get("install", []):
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        if name.lower() in EXCLUDED:
            continue
        resolved[name] = metadata["version"]
    return dict(sorted(resolved.items(), key=lambda pair: pair[0].lower()))


def sdist_for(name: str, version: str) -> tuple[str, str]:
    """Return (url, sha256) of the PyPI sdist, falling back to a pure-python wheel."""
    url = PYPI_URL.format(name=name, version=version)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.URLError as exc:
        raise ReleaseError(f"PyPI lookup failed for {name} {version}: {exc}") from exc

    files = payload.get("urls", [])
    for entry in files:
        if entry.get("packagetype") == "sdist":
            return entry["url"], entry["digests"]["sha256"]
    for entry in files:
        # A few projects ship wheels only; a pure-python wheel still installs.
        if entry.get("packagetype") == "bdist_wheel" and "py3-none-any" in entry["filename"]:
            return entry["url"], entry["digests"]["sha256"]
    raise ReleaseError(
        f"{name} {version} publishes neither an sdist nor a pure-python wheel; "
        "it needs a hand-written resource block or a platform guard."
    )


def render_resources(packages: dict[str, str]) -> str:
    blocks = []
    for name, version in packages.items():
        url, digest = sdist_for(name, version)
        blocks.append(
            f'  resource "{name}" do\n'
            f'    url "{url}"\n'
            f'    sha256 "{digest}"\n'
            f"  end\n"
        )
    return "\n".join(blocks)


def splice(formula: str, version: str, tarball_sha: str, resources: str) -> str:
    formula = re.sub(
        r'^(\s*)url "https://github\.com/naveenreddyalka/daari/archive[^"]*"',
        rf'\1url "{TARBALL_URL.format(version=version)}"',
        formula,
        count=1,
        flags=re.MULTILINE,
    )
    formula = re.sub(
        r'^(\s*)sha256 "[0-9a-f]{64}"',
        rf'\1sha256 "{tarball_sha}"',
        formula,
        count=1,
        flags=re.MULTILINE,
    )
    # Resources live between the last depends_on line and the install block.
    marker = "  def install"
    if marker not in formula:
        raise ReleaseError("formula has no `def install` block to anchor resources against")
    head, _, tail = formula.partition(marker)
    head = re.sub(r"\n  resource \"[^\"]+\" do\n(?:.*?\n)?  end\n", "\n", head, flags=re.DOTALL)
    head = head.rstrip("\n") + "\n\n"
    return f"{head}{resources}\n{marker}{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release version, e.g. 1.2.0")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report whether the formula is already current; write nothing.",
    )
    args = parser.parse_args(argv)

    formula = FORMULA_PATH.read_text(encoding="utf-8")

    if args.check:
        if PLACEHOLDER_SHA in formula:
            print("formula sha256 is still the placeholder — run without --check")
            return 1
        if 'resource "' not in formula:
            print("formula declares no resources — dependencies would not install")
            return 1
        print("formula looks filled in")
        return 0

    try:
        tarball_sha = sha256_of_url(TARBALL_URL.format(version=args.version))
        packages = resolve_runtime_dependencies()
        print(f"resolved {len(packages)} runtime dependencies", file=sys.stderr)
        resources = render_resources(packages)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    FORMULA_PATH.write_text(
        splice(formula, args.version, tarball_sha, resources), encoding="utf-8"
    )
    print(f"updated {FORMULA_PATH.relative_to(REPO_ROOT)} for v{args.version}")
    print(f"  tarball sha256: {tarball_sha}")
    print(f"  resources:      {len(packages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
