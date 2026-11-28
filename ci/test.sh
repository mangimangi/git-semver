#!/bin/bash
# ci/test.sh - the step of git-semver's own `test` job: pytest under coverage,
# the coverage gate, and the bats tests of the shell scripts.
#
# Coverage measures the two shipped Python scripts, git-semver and release
# (pyproject.toml, [tool.coverage.*]), including runs a test starts as a
# subprocess; this script combines the per-process data, prints the per-file
# report with missing lines, and fails when the total or either file is below
# 99%. Then it runs the bats tests under tests/bats/.
#
# Uses the virtualenv (and the bats linked into it) that ci/setup.sh creates
# for the Python floor. When setup was skipped (a local `git-cicd check`
# without --setup), falls back to a python3 that already has pytest, pyyaml and
# coverage 7.10+, and a bats on PATH. Every part runs even when an earlier one
# fails; the exit status is non-zero when any failed.
set -euo pipefail

FLOOR="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n1)"
VENV="${XDG_CACHE_HOME:-$HOME/.cache}/git-semver-ci/venv-$FLOOR"
MIN_COVERAGE=99
COVERED=(git-semver release)
SETUP_HINT="run: .vendored/pkg/git-cicd/git-cicd check --setup"

if [ -n "$FLOOR" ] && [ -x "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
elif python3 -c "import pytest, yaml, coverage, sys; sys.exit(coverage.version_info < (7, 10))" 2>/dev/null; then
    PYTHON=python3
else
    echo "ci/test.sh: pytest, pyyaml or coverage 7.10+ is not installed; $SETUP_HINT" >&2
    exit 1
fi

if [ -n "$FLOOR" ] && [ -x "$VENV/bin/bats" ]; then
    BATS="$VENV/bin/bats"
elif BATS="$(command -v bats 2>/dev/null)"; then
    :
else
    echo "ci/test.sh: bats is not installed; $SETUP_HINT" >&2
    exit 1
fi

"$PYTHON" --version
status=0

"$PYTHON" -m coverage erase
"$PYTHON" -m coverage run -m pytest tests/ -v || status=1
"$PYTHON" -m coverage combine --quiet || status=1
"$PYTHON" -m coverage report --fail-under="$MIN_COVERAGE" || {
    echo "ci/test.sh: total line coverage is below $MIN_COVERAGE%" >&2
    status=1
}
for file in "${COVERED[@]}"; do
    if ! total="$("$PYTHON" -m coverage report --include="$file" --format=total \
            --fail-under="$MIN_COVERAGE")"; then
        echo "ci/test.sh: $file is at ${total:-no}% line coverage, below $MIN_COVERAGE%" >&2
        status=1
    fi
done

"$BATS" tests/bats || status=1
exit "$status"
