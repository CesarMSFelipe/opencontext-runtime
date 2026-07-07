#!/usr/bin/env bash
# Clean-install user acceptance: prove the product works the way a user gets it.
#
# Installs the packages into a FRESH venv from the built wheels (no editable, no
# PYTHONPATH tricks), then drives the full post-install journey against an
# isolated $HOME and a throwaway project. Every step must pass. This catches the
# class of bug the PYTHONPATH-based e2e suite cannot: missing package-data, broken
# console entry points, and any flow that only works from the source tree.
#
# Usage:  bash scripts/clean_install_acceptance.sh
# Exit 0 = the installed product works end to end.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
VE="$WORK/ve"
HOME_DIR="$WORK/home"
PROJ="$WORK/proj"
FAILS=0

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

log()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
check() { # name; then a command via "$@"
  local name="$1"; shift
  if "$@" >"$WORK/$name.log" 2>&1; then
    printf '  \033[32mPASS\033[0m %s\n' "$name"
  else
    printf '  \033[31mFAIL\033[0m %s (see below)\n' "$name"; tail -6 "$WORK/$name.log" | sed 's/^/      /'
    FAILS=$((FAILS+1))
  fi
}

log "Fresh venv + real install (no -e, no PYTHONPATH)"
python3 -m venv "$VE"
"$VE/bin/pip" -q install --upgrade pip >/dev/null
"$VE/bin/pip" install --no-cache-dir \
  "$REPO_ROOT/packages/opencontext_core" \
  "$REPO_ROOT/packages/opencontext_profiles" \
  "$REPO_ROOT/packages/opencontext_memory" \
  "$REPO_ROOT/packages/opencontext_sdd" \
  "$REPO_ROOT/packages/opencontext_cli" >"$WORK/install.log" 2>&1 \
  || { echo "install FAILED"; tail -20 "$WORK/install.log"; exit 1; }

# A real Python project the user runs `oc run` against has a test runner in its
# environment; the runtime resolves it to verify the fix. Install pytest into the
# runtime venv so the `run` step exercises the full mutate->verify->pass path.
"$VE/bin/pip" -q install pytest >>"$WORK/install.log" 2>&1

OC="$VE/bin/opencontext"
mkdir -p "$HOME_DIR" "$PROJ"
printf 'def add(a, b):\n    return a - b\n' > "$PROJ/calc.py"
printf 'from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n' > "$PROJ/test_calc.py"
( cd "$PROJ" && git init -q 2>/dev/null || true )

# Run oc in the isolated environment: temp HOME, no inherited PYTHONPATH.
oc() { ( cd "$PROJ" && env -u PYTHONPATH HOME="$HOME_DIR" USERPROFILE="$HOME_DIR" \
         OPENCONTEXT_STORAGE_MODE=local "$OC" "$@" ); }

# opencode's launcher self-locates under $HOME/.opencode; link the real runtime.
[ -d "$HOME/.opencode" ] && ln -s "$HOME/.opencode" "$HOME_DIR/.opencode" 2>/dev/null || true

log "Post-install user journey"
check version    oc --version
check doctor     oc doctor --json
check init       oc init --non-interactive
check setup      oc setup claude-code --scope local --non-interactive
check index      oc index .
check pack       oc pack . --query "add function" --format json

# Wire the deterministic test_stub executor so `run` exercises the real
# mutation+verify path on a clean install. Without a configured executor the
# honest contract is `needs_executor` (exit 5, AC-009) — not a failure, but this
# gate proves the productive path end to end. Config mirrors the acceptance
# suite's stub setup (tests/acceptance/helpers/workspace.py).
cat > "$PROJ/opencontext.yaml" <<'YAML'
runtime:
  oc_flow_enabled: true
  gateway_enabled: true
  durable_artifacts: true
provider: test_stub
edits_file: provider_stub.json
YAML
cat > "$PROJ/provider_stub.json" <<'JSON'
[
  {
    "path": "calc.py",
    "operation": "replace_range",
    "start_line": 2,
    "end_line": 2,
    "content": "    return a + b",
    "reason": "fix add: return the sum of its arguments",
    "requirement_refs": ["add returns the sum of its arguments"]
  }
]
JSON
check run        oc run "Fix failing test" --json
check mem_save   oc memory v2 save --title "Pref" --content "prefers pytest" --type preference
check mem_search oc memory v2 search --query "pytest"
check mem_doctor oc memory v2 doctor
check sdd_new    oc sdd new "add-multiply"
check sdd_status oc sdd status
check uninstall  oc uninstall claude-code --purge --full --verify --yes --root "$PROJ"

# The strong uninstall must leave zero OpenContext *config* traces. It must NOT
# delete user content: source files, .git, and the openspec/ SDD artifact store
# (proposals/specs the user authored via `sdd new`) are the user's, not OC's.
LEFT="$(cd "$PROJ" && ls -a | grep -Ev '^\.$|^\.\.$|^calc.py$|^test_calc.py$|^provider_stub.json$|^\.git$|^openspec$' | tr '\n' ' ')"
if [ -n "$LEFT" ]; then
  printf '  \033[31mFAIL\033[0m uninstall left traces: %s\n' "$LEFT"; FAILS=$((FAILS+1))
else
  printf '  \033[32mPASS\033[0m uninstall left zero traces\n'
fi

log "Result"
if [ "$FAILS" -eq 0 ]; then
  echo "ALL PASS — the installed product works end to end."; exit 0
else
  echo "$FAILS step(s) FAILED."; exit 1
fi
