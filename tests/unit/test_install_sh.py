from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "scripts" / "install.sh"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
BASH = shutil.which("bash") or "/bin/bash"


def _safe_path(*extra: Path) -> str:
    """PATH with coreutils + optional fakes — never Homebrew or the user ollama."""
    parts = [str(path) for path in extra]
    parts.append(str(Path(BASH).parent))
    parts.extend(["/bin", "/usr/bin"])
    return ":".join(parts)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _fake_python312(bin_dir: Path) -> None:
    _write_executable(
        bin_dir / "python3.12",
        """#!/bin/sh
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
  dest="$3"
  mkdir -p "$dest/bin"
  cat > "$dest/bin/activate" <<'ACT'
# fake activate
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
export PATH="${SCRIPT_DIR}:$PATH"
ACT
  cat > "$dest/bin/pip" <<'PIP'
#!/bin/sh
echo "fake-pip $*"
exit 0
PIP
  cat > "$dest/bin/daari" <<'DAARI'
#!/bin/sh
if [ "$1" = "--help" ]; then
  echo "Usage: daari"
  exit 0
fi
if [ "$1" = "doctor" ]; then
  echo "doctor skipped in fake venv"
  exit 0
fi
echo "daari $*"
exit 0
DAARI
  chmod +x "$dest/bin/pip" "$dest/bin/daari"
  exit 0
fi
echo "unexpected python3.12 $*" >&2
exit 1
""",
    )


@pytest.fixture
def isolated_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(INSTALL_SH, repo / "scripts" / "install.sh")
    (repo / "scripts" / "install.sh").chmod(INSTALL_SH.stat().st_mode)
    (repo / "pyproject.toml").write_text("[project]\nname='daari'\n", encoding="utf-8")
    bins = tmp_path / "bin"
    bins.mkdir()
    _fake_python312(bins)
    env = os.environ.copy()
    env["PATH"] = _safe_path(bins)
    env["RUN_DOCTOR"] = "0"
    return repo, bins, env


class TestInstallSh:
    def test_syntax(self):
        subprocess.run([BASH, "-n", str(INSTALL_SH)], check=True)

    def test_fails_without_python312(self, isolated_repo, tmp_path):
        repo, _bins, env = isolated_repo
        empty = tmp_path / "empty"
        empty.mkdir()
        env = {**env, "PATH": _safe_path(empty)}
        result = subprocess.run(
            [BASH, str(repo / "scripts" / "install.sh")],
            cwd=repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Python 3.12 required" in result.stderr

    def test_creates_venv_and_skips_ollama(self, isolated_repo):
        repo, _bins, env = isolated_repo
        result = subprocess.run(
            [BASH, str(repo / "scripts" / "install.sh")],
            cwd=repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert (repo / ".venv").is_dir()
        assert (repo / ".venv" / "bin" / "daari").is_file()
        assert "Ollama not found" in result.stdout
        assert "daari serve" in result.stdout
        assert "ollama pull" in result.stdout

    def test_pull_l4_flag_invokes_ollama(self, isolated_repo):
        repo, bins, env = isolated_repo
        pulls = repo / "pulls.log"
        _write_executable(
            bins / "ollama",
            f"""#!/bin/sh
echo "$*" >> "{pulls}"
exit 0
""",
        )
        env = {**env, "PULL_L4": "1", "PULL_L5": "0"}
        result = subprocess.run(
            [BASH, str(repo / "scripts" / "install.sh")],
            cwd=repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        recorded = pulls.read_text(encoding="utf-8")
        assert "pull llama3.2:3b" in recorded
        assert "pull llama3.1:8b" in recorded
        assert "llama3.1:70b" not in recorded


class TestInstallCiGate:
    def test_ci_runs_fresh_clone_installer(self):
        data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
        jobs = data["jobs"]
        assert "install" in jobs, "CI must have an install job that gates scripts/install.sh"
        steps = jobs["install"]["steps"]
        rendered = yaml.safe_dump(steps)
        assert "scripts/install.sh" in rendered
        assert "RUN_DOCTOR=0" in rendered
        assert "daari --help" in rendered or ".venv/bin/daari --help" in rendered
