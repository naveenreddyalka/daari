"""Homebrew formula updater (issue #160).

The network-dependent halves (release tarball hash, PyPI sdist lookup) are
exercised by running the script against a real tag; these tests pin the pure
rewriting logic, where a silent mistake ships a formula that cannot install.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

FORMULA_STUB = """\
class Daari < Formula
  desc "Local-first LLM execution router"
  url "https://github.com/naveenreddyalka/daari/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end
end
"""

RESOURCES = """\
  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/aa/bb/pyyaml-6.0.3.tar.gz"
    sha256 "aaaabbbbccccddddeeeeffff00001111222233334444555566667777888899990"
  end
"""


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "update_formula", REPO_ROOT / "scripts" / "update_formula.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_formula"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return _load_module()


def test_splice_replaces_url_and_hash(module):
    out = module.splice(FORMULA_STUB, "1.2.0", "a" * 64, RESOURCES)
    assert "refs/tags/v1.2.0.tar.gz" in out
    assert f'sha256 "{"a" * 64}"' in out
    assert module.PLACEHOLDER_SHA not in out, "placeholder must not survive"


def test_splice_inserts_resources_before_install(module):
    out = module.splice(FORMULA_STUB, "1.2.0", "a" * 64, RESOURCES)
    assert out.index('resource "pyyaml"') < out.index("def install")
    assert out.index("depends_on") < out.index('resource "pyyaml"')


def test_splice_is_idempotent(module):
    """Re-running for a new version must not stack duplicate resource blocks."""
    once = module.splice(FORMULA_STUB, "1.2.0", "a" * 64, RESOURCES)
    twice = module.splice(once, "1.3.0", "b" * 64, RESOURCES)
    assert twice.count('resource "pyyaml"') == 1
    assert "refs/tags/v1.3.0.tar.gz" in twice
    assert "v1.2.0" not in twice


def test_splice_refuses_a_formula_it_cannot_anchor(module):
    with pytest.raises(module.ReleaseError, match="def install"):
        module.splice("class Daari < Formula\nend\n", "1.2.0", "a" * 64, RESOURCES)


def test_checked_in_formula_is_filled_in(module):
    """Guards against shipping the placeholder that blocked #160 for 3 releases."""
    formula = (REPO_ROOT / "Formula" / "daari.rb").read_text(encoding="utf-8")
    assert module.PLACEHOLDER_SHA not in formula, "release hash is still a placeholder"
    assert formula.count('resource "') >= 25, (
        "virtualenv_install_with_resources installs only declared resources, so a "
        "formula without them builds a daari that cannot import its dependencies"
    )


def test_excluded_packages_never_become_resources(module):
    assert "daari" in module.EXCLUDED
    assert "pip" in module.EXCLUDED
