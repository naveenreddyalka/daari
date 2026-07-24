# Homebrew formula for daari (issue #123).
# Install from this repo: brew install --formula ./Formula/daari.rb
# Or after a tap: brew install naveenreddyalka/daari/daari
class Daari < Formula
  desc "Local-first LLM execution router — cache before cloud"
  homepage "https://github.com/naveenreddyalka/daari"
  url "https://github.com/naveenreddyalka/daari/archive/refs/tags/v1.2.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "Apache-2.0"
  head "https://github.com/naveenreddyalka/daari.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "daari", shell_output("#{bin}/daari --help")
  end
end
