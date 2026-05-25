#!/usr/bin/env bash
# OpenContext Runtime Installer
# One-liner: curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash

set -euo pipefail

OPENCONTEXT_VERSION="0.3.0"
REPO_URL="https://github.com/CesarMSFelipe/OpenContext-Runtime"
VENV_DIR="${HOME}/.opencontext/venv"
BIN_DIR="${HOME}/.local/bin"

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
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
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

# Detect PEP 668 externally-managed environment
is_externally_managed() {
    # Check for PEP 668 marker file or pip error code
    if [ -f "$($PYTHON_CMD -c 'import sys; print(sys.prefix)')/EXTERNALLY-MANAGED" ] 2>/dev/null; then
        return 0
    fi
    # Also check via pip dry-run (Ubuntu/Debian may not create the marker file)
    if ! "$PYTHON_CMD" -m pip install --dry-run pip 2>/dev/null | grep -q "externally-managed"; then
        return 1
    fi
    return 0
}

create_venv() {
    echo ""
    echo "Creating virtual environment at $VENV_DIR ..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
}

# Determine pip command to use (system or venv)
get_pip_cmd() {
    if [ -f "$VENV_DIR/bin/pip" ]; then
        echo "$VENV_DIR/bin/python -m pip"
    elif [ -f "$VENV_DIR/Scripts/pip.exe" ]; then
        echo "$VENV_DIR/Scripts/python -m pip"
    else
        echo "$PYTHON_CMD -m pip"
    fi
}

# Determine python command to use
get_python_cmd() {
    if [ -f "$VENV_DIR/bin/python" ]; then
        echo "$VENV_DIR/bin/python"
    elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then
        echo "$VENV_DIR/Scripts/python.exe"
    else
        echo "$PYTHON_CMD"
    fi
}

install_opencontext() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          OpenContext Runtime Installer v${OPENCONTEXT_VERSION}          ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    check_python
    check_pip

    PIP_CMD=$(get_pip_cmd)
    PY_CMD=$(get_python_cmd)

    echo ""

    # Check if we need a virtual environment (PEP 668)
    if is_externally_managed; then
        echo "⚠ Externally-managed Python environment detected (PEP 668)."
        echo "  OpenContext will be installed in an isolated virtual environment."
        echo ""

        if [ ! -d "$VENV_DIR" ]; then
            if [ "$YES_MODE" = true ]; then
                create_venv
            else
                read -rp "Create virtual environment at $VENV_DIR? [Y/n] " answer
                case "$answer" in
                    [Nn]*)
                        echo "Installation cancelled."
                        echo ""
                        echo "Alternatives:"
                        echo "  1. Use pipx:  pipx install opencontext-cli"
                        echo "  2. Use --break-system-packages (not recommended)"
                        echo "  3. Run with --yes to auto-create the venv"
                        exit 0
                        ;;
                    *)
                        create_venv
                        ;;
                esac
            fi
        fi

        # Re-resolve commands after venv creation
        PIP_CMD=$(get_pip_cmd)
        PY_CMD=$(get_python_cmd)
    fi

    echo ""
    echo "Installing OpenContext packages..."
    echo ""

    # Try pip install first (when published)
    if $PIP_CMD install opencontext-core opencontext-cli --quiet 2>/dev/null; then
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
        $PIP_CMD install -e packages/opencontext_core -e packages/opencontext_cli --quiet
        echo "✓ Installed from source"
    fi

    # Create wrapper script in ~/.local/bin if using venv
    if [ -d "$VENV_DIR" ]; then
        mkdir -p "$BIN_DIR"
        VENV_PYTHON=$(get_python_cmd)
        cat > "$BIN_DIR/opencontext" <<EOF
#!/usr/bin/env bash
exec $VENV_PYTHON -m opencontext_cli "\$@"
EOF
        chmod +x "$BIN_DIR/opencontext"
        echo "✓ Created wrapper: $BIN_DIR/opencontext"
    fi

    # Check if opencontext is in PATH
    if ! command -v opencontext &>/dev/null; then
        echo ""
        echo "⚠ 'opencontext' is not in your PATH."
        echo "  Add this to your shell profile:"
        echo "    export PATH=\"\$PATH:$BIN_DIR\""
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
