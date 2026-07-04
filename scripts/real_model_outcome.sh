#!/usr/bin/env bash
# Real-model OUTCOME proof: a real model, in a real host, drives an OpenContext
# flow to actually fix a bug and make its failing test pass — not just call a tool.
#
# Usage:  bash scripts/real_model_outcome.sh <host> <workflow> <tdd> <model>
#   host      = opencode | codex | claude
#   workflow  = sdd | oc-flow
#   tdd       = strict | off
#   model     = provider/model string for that host
#
# Exit 0 = the bug was fixed AND the test passes (outcome achieved).
# Writes evidence line to artifacts/real-model-matrix.jsonl
set -uo pipefail

HOST="${1:?host}"; WORKFLOW="${2:?workflow}"; TDD="${3:?tdd}"; MODEL="${4:?model}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_HOME="$HOME"
WORK="$(mktemp -d /tmp/oc-outcome.XXXXXX)"; [ -n "$WORK" ] || exit 1
PROJ="$WORK/proj"; mkdir -p "$PROJ"
cleanup() { rm -rf "$WORK"; }   # only the temp workdir; never a real HOME
trap cleanup EXIT

# Per-host HOME + credential wiring. Config isolation matters (don't pollute the
# user's global agent config), but the host still needs its own auth:
#   opencode -> isolated HOME + symlink the real ~/.opencode runtime (holds auth)
#   codex    -> isolated HOME; auth.json copied in after setup writes config.toml
#   claude   -> real HOME (its MCP is project-scoped, so no global pollution) so
#               the existing login is used; only the temp project is written to
case "$HOST" in
  opencode)
    HOME_T="$WORK/home"; mkdir -p "$HOME_T"
    [ -d "$REAL_HOME/.opencode" ] && ln -s "$REAL_HOME/.opencode" "$HOME_T/.opencode" ;;
  codex)
    HOME_T="$WORK/home"; mkdir -p "$HOME_T/.codex" ;;
  claude)
    HOME_T="$REAL_HOME" ;;
  *) echo "unknown host $HOST"; exit 2 ;;
esac

export HOME="$HOME_T" USERPROFILE="$HOME_T"
export OPENCONTEXT_STORAGE_MODE=local
export OPENCONTEXT_TDD_MODE="$TDD"
PP=""; for p in opencontext_core opencontext_cli opencontext_memory opencontext_sdd opencontext_profiles; do
  PP="$PP:$REPO_ROOT/packages/$p"; done
export PYTHONPATH="${PYTHONPATH:-}${PP}"
OC="$REPO_ROOT/.venv/bin/opencontext"; [ -x "$OC" ] || OC="opencontext"

# Buggy source + a test that fails until add() is fixed.
printf 'def add(a, b):\n    return a - b\n' > "$PROJ/calc.py"
printf 'from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n' > "$PROJ/test_calc.py"
( cd "$PROJ" && git init -q 2>/dev/null || true )
# Pin tdd in the project config too, so the run respects it regardless of env inheritance.
printf 'harness:\n  tdd_mode: %s\n' "$TDD" > "$PROJ/opencontext.yaml"

# The setup agent id differs from the host binary name for claude.
SETUP_AGENT="$HOST"; [ "$HOST" = "claude" ] && SETUP_AGENT="claude-code"
env -u PYTHONPATH HOME="$HOME_T" USERPROFILE="$HOME_T" OPENCONTEXT_STORAGE_MODE=local \
  "$OC" setup "$SETUP_AGENT" --scope local --yes --non-interactive --root "$PROJ" \
  > "$WORK/setup.log" 2>&1 || { echo "setup $SETUP_AGENT FAILED"; tail -5 "$WORK/setup.log"; exit 1; }

# Provision credentials the isolated HOME lacks (codex reads ~/.codex/auth.json).
if [ "$HOST" = "codex" ] && [ -f "$REAL_HOME/.codex/auth.json" ]; then
  cp -f "$REAL_HOME/.codex/auth.json" "$HOME_T/.codex/auth.json"
fi
# claude: pre-approve the project MCP server so headless reaches the tools.
if [ "$HOST" = "claude" ]; then
  mkdir -p "$PROJ/.claude"
  printf '{"enableAllProjectMcpServers": true}' > "$PROJ/.claude/settings.local.json"
fi

PROMPT="This project has a bug. calc.py's add() returns a - b, so test_calc.py fails.
You MUST fix it by driving the OpenContext MCP flow. Do NOT edit any file before step 1.
1. FIRST call the opencontext_run tool with: task='fix add so test_calc passes', workflow='$WORKFLOW', root='$PROJ'. Do this before touching any file.
2. It returns status 'agent_execute' with a follow_up describing the edit. NOW make the code edit yourself: change add to 'return a + b'.
3. Call opencontext_session_apply with the follow_up.arguments; set payload.changed_files=['calc.py'] and payload.test_command=['python','-m','pytest','-q','test_calc.py']. The run must reach status 'completed'.
Report the final run status and confirm the test passes. Using opencontext_run is mandatory; a direct edit without it does not count."

log_turn="$WORK/turn.log"
case "$HOST" in
  opencode)
    ( cd "$PROJ" && timeout 420 opencode run --model "$MODEL" --format json "$PROMPT" ) \
      > "$log_turn" 2>&1 ;;
  codex)
    # This box's bubblewrap cannot create user namespaces (RTM_NEWADDR denied), so
    # codex's sandbox would fail to even spawn the MCP server. The project is an
    # isolated throwaway temp dir, so bypassing the sandbox is safe here.
    ( cd "$PROJ" && timeout 420 codex exec -m "$MODEL" \
        --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "$PROMPT" ) \
      > "$log_turn" 2>&1 ;;
  claude)
    ( cd "$PROJ" && timeout 420 claude -p --model "$MODEL" \
        --mcp-config "$PROJ/.mcp.json" --dangerously-skip-permissions "$PROMPT" ) \
      > "$log_turn" 2>&1 ;;
  *) echo "unknown host $HOST"; exit 2 ;;
esac

# --- Outcome verification (host-agnostic) ---
FIXED=false; TESTPASS=false; FLOW=false
grep -Eq 'return a \+ b|return b \+ a' "$PROJ/calc.py" && FIXED=true
( cd "$PROJ" && env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
    "$REPO_ROOT/.venv/bin/python" -m pytest -q test_calc.py ) >/dev/null 2>&1 && TESTPASS=true
# Flow engaged: the transcript invoked an opencontext tool, or a run receipt exists.
grep -q 'opencontext_' "$log_turn" && FLOW=true
if ls "$PROJ/.opencontext/runs"/* >/dev/null 2>&1 || ls "$HOME_T/.opencontext/runs"/* >/dev/null 2>&1; then
  FLOW=true; fi

OK=false; { [ "$FIXED" = true ] && [ "$TESTPASS" = true ]; } && OK=true
mkdir -p "$REPO_ROOT/artifacts"
printf '{"host":"%s","workflow":"%s","tdd":"%s","model":"%s","fixed":%s,"test_passes":%s,"flow_engaged":%s,"outcome_ok":%s}\n' \
  "$HOST" "$WORKFLOW" "$TDD" "$MODEL" "$FIXED" "$TESTPASS" "$FLOW" "$OK" \
  | tee -a "$REPO_ROOT/artifacts/real-model-matrix.jsonl"

if [ "$OK" = true ]; then exit 0; else
  echo "--- turn tail (debug) ---"; tail -15 "$log_turn"; exit 1; fi
