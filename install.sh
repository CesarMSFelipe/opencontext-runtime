#!/usr/bin/env bash
# OpenContext Runtime Installer
# One-liner: curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash

set -euo pipefail

OPENCONTEXT_VERSION="1.2.0"
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
    # 1. Check for PEP 668 marker file in stdlib path
    local stdlib_path
    stdlib_path=$("$PYTHON_CMD" -c 'import sysconfig; print(sysconfig.get_path("stdlib"))' 2>/dev/null)
    if [ -n "$stdlib_path" ] && [ -f "$stdlib_path/EXTERNALLY-MANAGED" ]; then
        return 0
    fi

    # 2. Check common system paths as fallback
    for path in "/usr/lib/python3"* "/usr/local/lib/python3"*; do
        if [ -f "$path/EXTERNALLY-MANAGED" ]; then
            return 0
        fi
    done

    # 3. Try a pip dry-run (most reliable way to know if pip will block us)
    if "$PYTHON_CMD" -m pip install --dry-run pip 2>&1 | grep -qiE "externally-managed|break-system-packages"; then
        return 0
    fi

    return 1
}

create_venv() {
    echo ""
    echo "Creating virtual environment at $VENV_DIR ..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
}

_add_venv_to_path() {
    local venv_bin="$1"
    local added=false
    for profile in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
        if [ -f "$profile" ]; then
            if ! grep -q "$venv_bin" "$profile" 2>/dev/null; then
                echo "" >> "$profile"
                echo "# OpenContext Runtime" >> "$profile"
                echo "export PATH=\"$venv_bin:\$PATH\"" >> "$profile"
                added=true
                echo "✓ Added to PATH in $(basename "$profile")"
            fi
        fi
    done
    if [ "$added" = false ]; then
        echo ""
        echo "⚠ Could not auto-configure PATH."
        echo "  Add this to your shell profile manually:"
        echo "    export PATH=\"$venv_bin:\$PATH\""
        echo ""
    fi
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

detect_pipx() {
    if command -v pipx &>/dev/null; then
        return 0
    fi
    return 1
}

install_via_pipx() {
    echo "  Installing via pipx..."
    pipx install "opencontext-cli==${OPENCONTEXT_VERSION}" || \
        pipx upgrade opencontext-cli || return 1
    return 0
}

install_via_pip() {
    local pip_cmd="$1"
    echo "  Installing via pip..."
    $pip_cmd install --upgrade --upgrade-strategy eager "opencontext-cli==${OPENCONTEXT_VERSION}" --quiet || return 1
    return 0
}

install_from_source() {
    local pip_cmd="$1"
    echo "  Installing from source (latest main)..."

    if ! command -v git &>/dev/null; then
        echo "Error: git is required for source installation."
        echo ""
        echo "Try: pip install opencontext-cli"
        exit 1
    fi

    TEMP_DIR=$(mktemp -d)
    git clone --depth 1 "$REPO_URL.git" "$TEMP_DIR/opencontext" 2>/dev/null || {
        echo "Error: Could not clone repository."
        echo "Try: pip install opencontext-cli"
        exit 1
    }

    (cd "$TEMP_DIR/opencontext" && $pip_cmd install -e packages/opencontext_core -e packages/opencontext_cli --quiet) || {
        echo "Error: Source installation failed."
        exit 1
    }
    echo "✓ Installed from source"
}

verify_install() {
    # Prefer venv binary over whatever is in PATH (avoids reporting a stale system install)
    local oc_bin=""
    if [ -f "$VENV_DIR/bin/opencontext" ]; then
        oc_bin="$VENV_DIR/bin/opencontext"
    elif [ -f "$VENV_DIR/Scripts/opencontext.exe" ]; then
        oc_bin="$VENV_DIR/Scripts/opencontext.exe"
    elif command -v opencontext &>/dev/null; then
        oc_bin="opencontext"
    fi

    if [ -n "$oc_bin" ]; then
        local version
        version=$("$oc_bin" --version 2>/dev/null || true)
        echo "✓ Verified: $version"
    else
        echo "⚠ 'opencontext' not found in PATH."
        echo "  If using a venv, activate it or add it to PATH."
    fi
}

install_opencontext() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          OpenContext Runtime Installer v${OPENCONTEXT_VERSION}          ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # pipx is the cleanest path — suggest it first
    if detect_pipx; then
        echo "✓ pipx detected"
        echo "  Run: pipx install opencontext-cli"
        echo "  (or continue with this installer for the full setup)"
        echo ""
        if [ "$YES_MODE" = false ]; then
            read -rp "Install via pipx instead? [y/N] " use_pipx
            case "$use_pipx" in
                [Yy]*)
                    install_via_pipx && { verify_install; show_finish; return; }
                    echo "  pipx install failed, falling back to pip..."
                    ;;
            esac
        fi
    fi

    check_python
    check_pip

    PIP_CMD=$(get_pip_cmd)
    PY_CMD=$(get_python_cmd)

    echo ""

    # Detect if we are running from within the OpenContext source tree
    IS_LOCAL=false
    if [ -f "packages/opencontext_core/pyproject.toml" ] && [ -f "packages/opencontext_cli/pyproject.toml" ]; then
        IS_LOCAL=true
        echo "✓ Running from local source tree"
    fi

    # Check if we need a virtual environment (PEP 668)
    if is_externally_managed; then
        echo "⚠ Externally-managed Python environment detected (PEP 668)."
        echo "  OpenContext will be installed in an isolated virtual environment."
        echo ""

        if [ ! -d "$VENV_DIR" ]; then
            if [ "$YES_MODE" = true ] || [ "$IS_LOCAL" = true ]; then
                create_venv
            else
                read -rp "Create virtual environment at $VENV_DIR? [Y/n] " answer
                case "$answer" in
                    [Nn]*)
                        echo "Installation cancelled."
                        echo ""
                        echo "Alternatives:"
                        echo "  1. pipx install opencontext-cli"
                        echo "  2. Run with --yes to auto-create venv"
                        exit 0
                        ;;
                    *)
                        create_venv
                        ;;
                esac
            fi
        fi

        PIP_CMD=$(get_pip_cmd)
        PY_CMD=$(get_python_cmd)
    fi

    echo ""
    echo "Installing OpenContext packages..."
    echo ""

    if [ "$IS_LOCAL" = true ]; then
        echo "Installing from current directory..."
        $PIP_CMD install -e packages/opencontext_core -e packages/opencontext_cli --quiet
        echo "✓ Installed from local source"
    else
        # Try PyPI first (fast path), fall back to source
        if install_via_pip "$PIP_CMD"; then
            echo "✓ Installed from PyPI"
        else
            echo "  PyPI install unavailable, falling back to source..."
            install_from_source "$PIP_CMD"
        fi
    fi

    # Ensure opencontext command is available from venv
    if [ -d "$VENV_DIR" ]; then
        VENV_BIN=""
        if [ -d "$VENV_DIR/bin" ]; then
            VENV_BIN="$VENV_DIR/bin"
        elif [ -d "$VENV_DIR/Scripts" ]; then
            VENV_BIN="$VENV_DIR/Scripts"
        fi

        if [ -n "$VENV_BIN" ] && [ -f "$VENV_BIN/opencontext" ]; then
            _add_venv_to_path "$VENV_BIN"
        fi
    fi

    # Remind user to reload shell if PATH was just updated
    if [ -d "$VENV_DIR" ] && ! command -v opencontext &>/dev/null; then
        echo ""
        echo "ℹ PATH updated. Run one of these to use 'opencontext' now:"
        echo "    source ~/.bashrc     # or ~/.zshrc"
        echo "    # or start a new terminal session"
        echo ""
    fi

    verify_install
    show_finish
}

show_finish() {
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
