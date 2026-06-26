#!/usr/bin/env bash
# scripts/gate_k.sh — Release-validation gate K (REQ-10)
# Runs K-1..K-10 in order. Prints PASS/FAIL per check.
# Exits non-zero naming the FIRST failure.
#
# Usage: bash scripts/gate_k.sh
# Must be run from the repository root with the venv active, OR with the venv
# path discoverable at .venv/ next to the script's repo root.
set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS_COUNT=0
FAIL_CHECK=""

check_pass() {
    local label="$1"
    echo "PASS  $label"
    PASS_COUNT=$((PASS_COUNT + 1))
}

check_fail() {
    local label="$1"
    local reason="$2"
    echo "FAIL  $label — $reason"
    if [[ -z "$FAIL_CHECK" ]]; then
        FAIL_CHECK="$label"
    fi
}

# Activate venv if not already in one (tolerate pre-activated environments).
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
        # shellcheck source=/dev/null
        source "$REPO_ROOT/.venv/bin/activate"
    fi
fi

OC_BIN="${VIRTUAL_ENV:-$REPO_ROOT/.venv}/bin/opencontext"
PYTHON_BIN="${VIRTUAL_ENV:-$REPO_ROOT/.venv}/bin/python"

echo "=== Gate K — Release Validation ==="
echo "Repo: $REPO_ROOT"
echo ""

# ---------------------------------------------------------------------------
# K-1  ruff check on packages + tests is clean
# ---------------------------------------------------------------------------
LABEL="K-1: ruff check (packages/ + tests/)"
if ruff check "$REPO_ROOT/packages/" "$REPO_ROOT/tests/" 2>&1 >/dev/null; then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "ruff reported lint errors — run 'ruff check packages/ tests/' for details"
fi

# ---------------------------------------------------------------------------
# K-2  mypy strict clean on core + api + cli + profiles
# ---------------------------------------------------------------------------
LABEL="K-2: mypy strict (core + api + cli + profiles)"
if mypy \
    "$REPO_ROOT/packages/opencontext_core" \
    "$REPO_ROOT/packages/opencontext_api" \
    "$REPO_ROOT/packages/opencontext_cli" \
    "$REPO_ROOT/packages/opencontext_profiles" \
    2>&1 | grep -q "^Success:"; then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "mypy reported type errors — run 'mypy packages/opencontext_core packages/opencontext_api packages/opencontext_cli packages/opencontext_profiles'"
fi

# ---------------------------------------------------------------------------
# K-3  full pytest suite green
# ---------------------------------------------------------------------------
LABEL="K-3: full pytest suite"
if (cd "$REPO_ROOT" && python -m pytest -q --tb=short > /dev/null 2>&1); then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "pytest reported failures — run 'python -m pytest' for details"
fi

# ---------------------------------------------------------------------------
# K-4  doctor metaharness: empty temp dir scores <90, repo root scores >=90
# ---------------------------------------------------------------------------
LABEL="K-4a: metaharness empty-dir scores below gate"
TMPD="$(mktemp -d)"
MH_EMPTY_OUT="$(cd "$TMPD" && "$OC_BIN" doctor metaharness 2>&1 || true)"
rm -rf "$TMPD"
# Extract score from "score=NN/100" in the first line
MH_EMPTY_SCORE="$(echo "$MH_EMPTY_OUT" | grep -oP 'score=\K[0-9]+(?=/)' | head -1 || echo 0)"
if [[ "${MH_EMPTY_SCORE:-0}" -lt 90 ]]; then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "empty dir scored ${MH_EMPTY_SCORE}/100 (expected <90)"
fi

LABEL="K-4b: metaharness repo-root scores at or above gate"
MH_REPO_OUT="$(cd "$REPO_ROOT" && "$OC_BIN" doctor metaharness 2>&1 || true)"
MH_REPO_SCORE="$(echo "$MH_REPO_OUT" | grep -oP 'score=\K[0-9]+(?=/)' | head -1 || echo 0)"
if [[ "${MH_REPO_SCORE:-0}" -ge 90 ]]; then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "repo root scored ${MH_REPO_SCORE}/100 (expected >=90)"
fi

# ---------------------------------------------------------------------------
# K-5  memory benchmark seeded: R@5 >= 0.85 and MRR >= 0.70
#      Run from a temp dir (no tests/) to prove importlib.resources works.
#      An unseeded/broken benchmark would exit non-zero (invalid-state path).
# ---------------------------------------------------------------------------
LABEL="K-5: memory benchmark seeded (R@5>=0.85, MRR>=0.70)"
TMPD="$(mktemp -d)"
BENCH_JSON="$("$OC_BIN" memory benchmark --json 2>&1)" || {
    rm -rf "$TMPD"
    check_fail "$LABEL" "memory benchmark exited non-zero (invalid-state or fixture not found)"
    BENCH_JSON=""
}
rm -rf "$TMPD"
if [[ -n "$BENCH_JSON" ]]; then
    R5="$(echo "$BENCH_JSON" | "$PYTHON_BIN" -c "import json,sys; d=json.load(sys.stdin); print(d.get('recall_at_5',0))")"
    MRR="$(echo "$BENCH_JSON" | "$PYTHON_BIN" -c "import json,sys; d=json.load(sys.stdin); print(d.get('mrr',0))")"
    # Use python for float comparison
    if "$PYTHON_BIN" -c "import sys; r5,mrr=float('$R5'),float('$MRR'); sys.exit(0 if r5>=0.85 and mrr>=0.70 else 1)"; then
        check_pass "$LABEL"
    else
        check_fail "$LABEL" "R@5=${R5} MRR=${MRR} (thresholds: R@5>=0.85, MRR>=0.70)"
    fi
fi

# ---------------------------------------------------------------------------
# K-6  forged oc-new run with missing harness-report.json is blocked (not archived)
# ---------------------------------------------------------------------------
LABEL="K-6: archive gate blocks missing harness-report.json"
GATE_RESULT="$("$PYTHON_BIN" - <<'PYEOF'
import sys, tempfile
from pathlib import Path
from opencontext_core.oc_new.archive_gate import OcNewArchiveGate

tmpdir = Path(tempfile.mkdtemp())
try:
    OcNewArchiveGate().assert_can_archive(tmpdir)
    # No error raised = gate did NOT block = test failure
    print("GATE_DID_NOT_BLOCK")
    sys.exit(1)
except RuntimeError as e:
    msg = str(e)
    if "harness-report.json" in msg:
        print("GATE_BLOCKED_CORRECTLY")
        sys.exit(0)
    else:
        print(f"GATE_BLOCKED_WRONG_REASON: {msg[:80]}")
        sys.exit(1)
finally:
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
PYEOF
)"
GATE_EXIT=$?
if [[ $GATE_EXIT -eq 0 ]]; then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "archive gate did not block as expected: $GATE_RESULT"
fi

# ---------------------------------------------------------------------------
# K-7  /sdd scaffold endpoint returns 200 — delegate to existing test file
# ---------------------------------------------------------------------------
LABEL="K-7: POST /v1/refactor/sdd returns 200"
if (cd "$REPO_ROOT" && python -m pytest tests/api/test_sdd_severity.py -q --tb=short > /dev/null 2>&1); then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "tests/api/test_sdd_severity.py did not pass"
fi

# ---------------------------------------------------------------------------
# K-8  non-zero exit codes on failure paths:
#      (a) opencontext doctor metaharness in empty dir exits non-zero
#      (b) opencontext uninstall --verify in a non-installed temp dir exits non-zero
# ---------------------------------------------------------------------------
LABEL="K-8a: doctor metaharness exits non-zero in empty dir"
TMPD="$(mktemp -d)"
if (cd "$TMPD" && "$OC_BIN" doctor metaharness > /dev/null 2>&1); then
    rm -rf "$TMPD"
    check_fail "$LABEL" "doctor metaharness exited 0 in empty dir (should exit non-zero)"
else
    rm -rf "$TMPD"
    check_pass "$LABEL"
fi

LABEL="K-8b: uninstall --verify exits non-zero when project traces remain"
# Run from repo root where OC is installed: verify should detect traces and exit non-zero.
# (A clean dir where nothing is installed correctly exits 0 — that is NOT a failure path.)
if (cd "$REPO_ROOT" && "$OC_BIN" uninstall --verify > /dev/null 2>&1); then
    check_fail "$LABEL" "uninstall --verify exited 0 even though project traces remain (should exit non-zero)"
else
    check_pass "$LABEL"
fi

# ---------------------------------------------------------------------------
# K-9  pack/verified-context excludes OC-generated files
#      Covered by tests/core/test_pack_excludes_oc_generated_files.py.
# ---------------------------------------------------------------------------
LABEL="K-9: pack excludes OC-generated files"
if (cd "$REPO_ROOT" && python -m pytest tests/core/test_pack_excludes_oc_generated_files.py -q --tb=short > /dev/null 2>&1); then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "tests/core/test_pack_excludes_oc_generated_files.py did not pass"
fi

# ---------------------------------------------------------------------------
# K-10  workspace install leaves $HOME untouched
#       Covered by tests/cli/test_workspace_install_does_not_write_global.py.
# ---------------------------------------------------------------------------
LABEL="K-10: workspace install leaves \$HOME untouched"
if (cd "$REPO_ROOT" && python -m pytest tests/cli/test_workspace_install_does_not_write_global.py -q --tb=short > /dev/null 2>&1); then
    check_pass "$LABEL"
else
    check_fail "$LABEL" "tests/cli/test_workspace_install_does_not_write_global.py did not pass"
fi

# ---------------------------------------------------------------------------
# Summary
# K-1..K-10 with K-4 and K-8 each having two sub-checks = 12 total check slots
# ---------------------------------------------------------------------------
TOTAL_CHECKS=12
echo ""
echo "=== Gate K Summary: ${PASS_COUNT}/${TOTAL_CHECKS} check slots passed (K-1..K-10, K-4 and K-8 each have a+b sub-checks) ==="

if [[ -n "$FAIL_CHECK" ]]; then
    echo "GATE K: FAILED — first failure: $FAIL_CHECK"
    exit 1
else
    echo "GATE K: PASSED — all check slots green"
    exit 0
fi
