#!/usr/bin/env bash
# OpenContext Runtime Installer
# One-liner: curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash

set -euo pipefail

OPENCONTEXT_VERSION="0.1.0"
REPO_URL="https://github.com/CesarMSFelipe/OpenContext-Runtime"

check_python() {
    PYTHON_CMD="${PYTHON_CMD:-python3}"
    if ! command -v "$PYTHON_CMD" &>/dev/null; then
        PYTHON_CMD="python"
        if ! command -v "$PYTHON_CMD" &>/dev/null; then
            echo "Error: Python 3 is required but not found."
            echo "Please install Python 3.12 or later."
            exit 1
        fi
    fi

    local py_version
    py_version=$("$PYTHON_CMD" --version 2>&1 | awk '{print $2}')
    local major minor
    major=$(echo "$py_version" | cut -d. -f1)
    minor=$(echo "$py_version" | cut -d. -f2)

    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 12 ]; }; then
        echo "Error: Python 3.12+ is required. Found: $py_version"
        exit 1
    fi

    echo "✓ Python $py_version"
}

check_pip() {
    if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
        echo "Error: pip is required but not found."
        echo "Please install pip for Python 3."
        exit 1
    fi
    echo "✓ pip"
}

install_opencontext() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          OpenContext Runtime Installer v${OPENCONTEXT_VERSION}          ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    check_python
    check_pip

    echo ""
    echo "Installing OpenContext packages..."
    echo ""

    # Try pip install first (when published)
    if "$PYTHON_CMD" -m pip install opencontext-core opencontext-cli --quiet 2>/dev/null; then
        echo "✓ Installed from PyPI"
    else
        echo "PyPI packages not found. Installing from source..."
        echo "This requires git."

        if ! command -v git &>/dev/null; then
            echo "Error: git is required for source installation."
            echo ""
            echo "Manual installation:"
            echo "  git clone $REPO_URL.git"
            echo "  cd OpenContext-Runtime"
            echo "  pip install -e packages/opencontext_core -e packages/opencontext_cli"
            exit 1
        fi

        local temp_dir
        temp_dir=$(mktemp -d)

        git clone --depth 1 "$REPO_URL.git" "$temp_dir/opencontext" 2>/dev/null || {
            echo "Error: Could not clone repository."
            echo ""
            echo "Manual installation:"
            echo "  git clone $REPO_URL.git"
            echo "  cd OpenContext-Runtime"
            echo "  pip install -e packages/opencontext_core -e packages/opencontext_cli"
            rm -rf "$temp_dir"
            exit 1
        }

        cd "$temp_dir/opencontext"
        "$PYTHON_CMD" -m pip install -e packages/opencontext_core -e packages/opencontext_cli --quiet
        echo "✓ Installed from source"
        echo ""
        echo "Note: Source install is active. To update:"
        echo "  cd $temp_dir/opencontext && git pull && pip install -e packages/opencontext_core -e packages/opencontext_cli"
    fi

    # Check if opencontext is in PATH
    if ! command -v opencontext &>/dev/null; then
        echo ""
        echo "Warning: 'opencontext' command not found in PATH."
        echo "You may need to add Python scripts directory to your PATH:"
        echo "  export PATH=\"\$PATH:\$HOME/.local/bin\""
        echo ""
    fi

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "OpenContext Runtime v${OPENCONTEXT_VERSION} is installed!"
    echo ""
    echo "Quick start:"
    echo "  1. cd your-project"
    echo "  2. opencontext onboard"
    echo "  3. opencontext index ."
    echo "  4. opencontext pack . --query 'Explain this code'"
    echo ""
    echo "Or use the interactive TUI:"
    echo "  opencontext tui"
    echo ""
    echo "Get help:"
    echo "  opencontext --help"
    echo "  opencontext --version"
    echo ""
    echo "For agent integration:"
    echo "  opencontext install              # Auto-detect agents"
    echo "  opencontext install --target claude,cursor"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
}

# Main
install_opencontext
