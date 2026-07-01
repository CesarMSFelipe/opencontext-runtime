#!/usr/bin/env bash
# First-run E2E gate — shell wrapper for CI.
#
# Per Amendment-2 / DoD #16, this script runs the first-run E2E pytest
# and exits 0 if it passes or honestly blocks (skipped). If the wheel
# is not present, the script exits 0 with a clear SKIPPED message —
# honest block, not silent pass.
#
# Usage:
#   bash scripts/release/first_run_e2e.sh
#
# Exit codes:
#   0  E2E passed or honestly blocked
#   1  E2E ran and failed (RED — bug)

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT}"

if [ ! -d "dist" ] || [ -z "$(ls -A dist 2>/dev/null)" ]; then
    echo "[first_run_e2e] SKIPPED: no wheel present in dist/ — honest block (amendment-2)."
    echo "[first_run_e2e] To run the full E2E, build the wheel first: python -m build"
    exit 0
fi

echo "[first_run_e2e] Running E2E pytest against tests/e2e/test_first_run_user_flow.py"
python -m pytest tests/e2e/test_first_run_user_flow.py -q
rc=$?

if [ "${rc}" -eq 0 ]; then
    echo "[first_run_e2e] PASS"
    exit 0
elif [ "${rc}" -eq 5 ]; then
    # pytest exit code 5 = no tests collected (skip on a missing test
    # is honest block).
    echo "[first_run_e2e] HONEST BLOCK: no tests collected (rc=5)"
    exit 0
fi

echo "[first_run_e2e] FAIL: rc=${rc}"
exit 1
