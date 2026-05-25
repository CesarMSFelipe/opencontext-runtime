#!/usr/bin/env bash
# OpenContext Runtime Installer
# One-liner: curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash

set -euo pipefail

OPENCONTEXT_VERSION="0.1.0"
REPO_URL="https://github.com/CesarMSFelipe/OpenContext-Runtime"

# Parse flags
YES_MODE=false
TEMP_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)
            YES_MODE=true
            shift
            ;;
        --help|-h)
            echo "OpenContext Runtime Installer v${OPENCONTEXT_VERSION}"
            echo ""
            echo "Usage: bash install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -y, --yes    Non-interactive mode (skip prompts)"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: bash install.sh [--yes]"
            exit 1
            ;;
    esac
done

# Cleanup handler — removes temp dir on exit
cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

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

        TEMP_DIR=$(mktemp -d)

        git clone --depth 1 "$REPO_URL.git" "$TEMP_DIR/opencontext" 2>/dev/null || {
            echo "Error: Could not clone repository."
            echo ""
            echo "Manual installation:"
            echo "  git clone $REPO_URL.git"
            echo "  cd OpenContext-Runtime"
            echo "  pip install -e packages/opencontext_core -e packages/opencontext_cli"
            exit 1
        }

        cd "$TEMP_DIR/opencontext"
        "$PYTHON_CMD" -m pip install -e packages/opencontext_core -e packages/opencontext_cli --quiet
        echo "✓ Installed from source"
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
    echo "  2. opencontext install"
    echo ""
    echo "This will auto-detect your project, configure SDD/TDD, index your"
    echo "code, and set up agent integrations — all in one step."
    echo ""
    echo "Get help:"
    echo "  opencontext --help"
    echo "  opencontext --version"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
}

# Main
install_opencontext
