"""Guided PyPI publish for daari (issue #160).

Everything here is automatable except one step: registering the trusted
publisher, which is a form under your own PyPI account. PyPI exposes no API for
it, and trusted publishing deliberately stores no token anywhere, so there is
nothing for a script to authenticate with. This walks up to that step, prints the
exact values the form needs, then does the rest.

    python scripts/release_pypi.py check                 # diagnose, change nothing
    python scripts/release_pypi.py publish --target testpypi
    python scripts/release_pypi.py publish --target pypi
    python scripts/release_pypi.py verify --version 1.2.0

`publish` reruns the failed job from the tag's own release run when one exists,
so the upload matches the tag rather than whatever main happens to be.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "publish.yml"
OWNER = "naveenreddyalka"
REPO = "daari"
PROJECT = "daari"

PUBLISHING_URL = "https://pypi.org/manage/account/publishing/"
TESTPYPI_PUBLISHING_URL = "https://test.pypi.org/manage/account/publishing/"

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m",
    "\033[33m",
    "\033[31m",
    "\033[2m",
    "\033[1m",
    "\033[0m",
)


def ok(text: str) -> None:
    print(f"{GREEN}  ok{RESET}   {text}")


def warn(text: str) -> None:
    print(f"{YELLOW} warn{RESET}   {text}")


def fail(text: str) -> None:
    print(f"{RED} fail{RESET}   {text}")


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True)  # noqa: S603
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed:\n{result.stderr.strip()}")
    return result


def project_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("could not read version from pyproject.toml")
    return match.group(1)


def published_versions(index: str = "pypi") -> set[str]:
    """Versions already on the index; empty set when the project does not exist."""
    host = "pypi.org" if index == "pypi" else "test.pypi.org"
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"https://{host}/pypi/{PROJECT}/json", timeout=30
        ) as response:
            return set(json.load(response).get("releases", {}))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return set()
        raise


def latest_publish_run() -> dict | None:
    result = run(
        "gh",
        "run",
        "list",
        "--workflow",
        WORKFLOW,
        "--limit",
        "1",
        "--json",
        "databaseId,conclusion,event,headBranch,displayTitle",
    )
    runs = json.loads(result.stdout)
    return runs[0] if runs else None


def publisher_hint() -> None:
    print()
    print(f"{BOLD}One manual step — register the trusted publisher{RESET}")
    print(f"{DIM}  No API exists for this, and no token is created or stored.{RESET}")
    print()
    print(f"  Open: {PUBLISHING_URL}")
    print("  Add a *pending* publisher (the project does not exist on PyPI yet):")
    print()
    for label, value in (
        ("PyPI Project Name", PROJECT),
        ("Owner", OWNER),
        ("Repository name", REPO),
        ("Workflow name", WORKFLOW),
        ("Environment name", "pypi"),
    ):
        print(f"    {label:<20} {BOLD}{value}{RESET}")
    print()
    print(f"{DIM}  These must match exactly — they are the OIDC claims the job sends.{RESET}")
    print()


def cmd_check(_args: argparse.Namespace) -> int:
    version = project_version()
    print(f"{BOLD}daari {version} — release readiness{RESET}\n")

    problems = 0

    if run("gh", "auth", "status", check=False).returncode == 0:
        ok("gh is authenticated")
    else:
        fail("gh is not authenticated — run `gh auth login`")
        problems += 1

    tags = run("git", "tag", "-l", f"v{version}").stdout.strip()
    if tags:
        ok(f"tag v{version} exists")
    else:
        warn(f"tag v{version} does not exist yet — see docs/RELEASING.md")

    live = published_versions("pypi")
    if not live:
        warn(f"{PROJECT} is not on PyPI yet — a *pending* publisher is required")
        problems += 1
    elif version in live:
        ok(f"{PROJECT} {version} is already on PyPI — nothing to publish")
        return 0
    else:
        ok(f"{PROJECT} is on PyPI (latest published: {max(live)})")

    last = latest_publish_run()
    if last is None:
        warn("no publish workflow runs found")
    elif last["conclusion"] == "success":
        ok(f"last publish run succeeded ({last['displayTitle']})")
    else:
        fail(
            f"last publish run {last['conclusion']} — {last['displayTitle']} "
            f"(run {last['databaseId']})"
        )
        problems += 1

    formula = (REPO_ROOT / "Formula" / "daari.rb").read_text(encoding="utf-8")
    if "0" * 64 in formula:
        fail("Homebrew formula still has a placeholder sha256")
        problems += 1
    elif formula.count('resource "') < 25:
        fail("Homebrew formula declares no dependency resources")
        problems += 1
    else:
        ok(f"Homebrew formula filled in ({formula.count('resource ')} resources)")

    if problems:
        publisher_hint()
        print(f"{BOLD}Then:{RESET} python scripts/release_pypi.py publish --target pypi\n")
    return 1 if problems else 0


def watch(run_id: str, timeout: int = 900) -> str:
    print(f"{DIM}  watching run {run_id}…{RESET}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run(
            "gh", "run", "view", run_id, "--json", "status,conclusion", check=False
        )
        if result.returncode == 0:
            state = json.loads(result.stdout)
            if state["status"] == "completed":
                return state["conclusion"] or "unknown"
        time.sleep(10)
    return "timed_out"


def diagnose(run_id: str) -> None:
    log = run("gh", "run", "view", run_id, "--log-failed", check=False).stdout
    if "invalid-publisher" in log:
        fail("PyPI rejected the OIDC token: no publisher matches these claims.")
        claims = re.findall(r"\* `(sub|environment|workflow_ref)`: `([^`]+)`", log)
        for name, value in claims:
            print(f"       {name}: {value}")
        publisher_hint()
    elif "File already exists" in log:
        fail(
            "this version is already on the index and cannot be overwritten — "
            "bump the version in pyproject.toml and cut a new tag"
        )
    else:
        fail("publish failed; last lines of the failing job:")
        print("\n".join(f"       {line}" for line in log.strip().splitlines()[-12:]))


def cmd_publish(args: argparse.Namespace) -> int:
    version = project_version()
    target = args.target

    if version in published_versions(target):
        fail(f"{PROJECT} {version} already exists on {target} and cannot be replaced")
        return 1

    if target == "testpypi":
        print(f"Dispatching a TestPyPI publish of {version} from main…")
        print(f"{DIM}  needs its own pending publisher with environment `testpypi`:{RESET}")
        print(f"{DIM}  {TESTPYPI_PUBLISHING_URL}{RESET}")
        run("gh", "workflow", "run", WORKFLOW, "-f", "repository=testpypi")
        time.sleep(8)
        last = latest_publish_run()
    else:
        last = latest_publish_run()
        if last and last["conclusion"] not in (None, "success") and last["event"] == "release":
            print(f"Rerunning the failed job from {last['displayTitle']}…")
            print(f"{DIM}  keeps the tag's ref, so the upload matches the tag{RESET}")
            run("gh", "run", "rerun", str(last["databaseId"]), "--failed")
            time.sleep(8)
        else:
            print(f"Dispatching a PyPI publish of {version} from main…")
            run("gh", "workflow", "run", WORKFLOW, "-f", "repository=pypi")
            time.sleep(8)
            last = latest_publish_run()

    if last is None:
        fail("could not find the workflow run that was just started")
        return 1

    run_id = str(last["databaseId"])
    conclusion = watch(run_id)
    if conclusion == "success":
        ok(f"published {PROJECT} {version} to {target}")
        print(f"\n{BOLD}Verify:{RESET} python scripts/release_pypi.py verify --version {version}\n")
        return 0

    fail(f"run {run_id} finished: {conclusion}")
    diagnose(run_id)
    return 1


def cmd_verify(args: argparse.Namespace) -> int:
    version = args.version or project_version()
    print(f"Installing {PROJECT}=={version} in a throwaway venv…")
    with tempfile.TemporaryDirectory() as tmp:
        venv = Path(tmp) / "venv"
        run(sys.executable, "-m", "venv", str(venv))
        pip, daari = venv / "bin" / "pip", venv / "bin" / "daari"
        install = run(
            str(pip), "install", "--quiet", f"{PROJECT}=={version}", check=False
        )
        if install.returncode != 0:
            fail(f"install failed:\n{install.stderr.strip()}")
            return 1
        ok("installed from the index")
        result = run(str(daari), "--help", check=False)
        if result.returncode != 0 or "daari" not in result.stdout:
            fail("the installed CLI does not run")
            return 1
        ok("`daari --help` runs from the installed package")
    print(f"\n{GREEN}{BOLD}pip install {PROJECT} works.{RESET}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Diagnose release readiness; change nothing.")

    publish = sub.add_parser("publish", help="Trigger the publish workflow and watch it.")
    publish.add_argument("--target", choices=("pypi", "testpypi"), default="pypi")

    verify = sub.add_parser("verify", help="Install from the index in a clean venv.")
    verify.add_argument("--version", default=None)

    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "publish": cmd_publish, "verify": cmd_verify}
    try:
        return handlers[args.command](args)
    except RuntimeError as exc:
        fail(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
