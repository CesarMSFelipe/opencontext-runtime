class Opencontext < Formula
  desc "Context Engineering for AI Agents — secure, zero-trust, token-efficient context runtime"
  homepage "https://github.com/CesarMSFelipe/OpenContext-Runtime"
  license "MIT"

  depends_on "pipx"

  on_macos do
    depends_on "python@3.12"
  end

  on_linux do
    depends_on "python@3.12"
  end

  stable do
    url "https://github.com/CesarMSFelipe/OpenContext-Runtime/archive/refs/tags/v0.2.1-beta.tar.gz"
    # Generate with: shasum -a 256 <archive>
    # sha256 "REPLACE_WITH_ACTUAL_SHA"
  end

  head do
    url "https://github.com/CesarMSFelipe/OpenContext-Runtime.git", branch: "main"
  end

  def install
    ENV["PIPX_HOME"] = prefix/".pipx"
    ENV["PIPX_BIN_DIR"] = bin

    system "pipx", "install", "--python", Formula["python@3.12"].opt_bin/"python3.12",
           "opencontext-cli"

    generate_completions_from_executable(bin/"opencontext", "--help", shell_parameter_format: :none)
  end

  test do
    assert_match "opencontext", shell_output("#{bin}/opencontext --version")
  end
end
