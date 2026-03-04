# Homebrew formula template — update URL and sha256 after PyPI release
class CastControl < Formula
  include Language::Python::Virtualenv

  desc "Cast local video files to Chromecast — CLI and retro TUI"
  homepage "https://github.com/YuriKovalov22/castlocal"
  url "https://files.pythonhosted.org/packages/source/c/castlocal/castlocal-0.1.0.tar.gz"
  sha256 "UPDATE_AFTER_PYPI_RELEASE"
  license "MIT"

  depends_on "python@3.12"
  depends_on "ffmpeg"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "usage", shell_output("#{bin}/cast --help")
  end
end
