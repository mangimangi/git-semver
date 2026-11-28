#!/bin/bash
# ci/setup.sh - setup for git-semver's own `test` job (see
# .vendored/configs/git-cicd.json).
#
# Reads the Python floor from requires-python in pyproject.toml, uses that
# Python if present (python3.X, the runner tool cache) or installs it with uv
# (itself installed into a small venv when missing), and installs the test-only
# dependencies (pytest, coverage 7.10+ for subprocess measurement, pyyaml) into
# a virtualenv the test step finds on disk. No Python version is written in the
# workflow or the config: this script is the only place that decides it.
#
# Also makes bats (bats-core) available to the test step as $VENV/bin/bats:
# the bats already on PATH when there is one, else bats-core v$BATS_VERSION
# cloned once into the cache.
#
# The runner tool cache is $RUNNER_TOOL_CACHE (GitHub sets it to
# /opt/hostedtoolcache, the default here).
set -euo pipefail

FLOOR="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n1)"
if [ -z "$FLOOR" ]; then
    echo "ci/setup.sh: cannot read requires-python (\">=X.Y\") from pyproject.toml" >&2
    exit 1
fi
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/git-semver-ci"
VENV="$CACHE/venv-$FLOOR"
TOOLS="$CACHE/tools"   # holds uv when it has to be installed
TOOL_CACHE="${RUNNER_TOOL_CACHE:-/opt/hostedtoolcache}"
BATS_VERSION=1.11.1
BATS_DIR="$CACHE/bats-core-$BATS_VERSION"

find_floor() {
    local candidate
    for candidate in "python$FLOOR" "$TOOL_CACHE"/Python/"$FLOOR".*/x64/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    local uv
    uv="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv" ] && python3 -m venv "$TOOLS" >&2 \
            && "$TOOLS/bin/python" -m pip install --quiet uv >&2; then
        uv="$TOOLS/bin/uv"
    fi
    if [ -n "$uv" ]; then
        "$uv" python install "$FLOOR" >&2 && "$uv" python find "$FLOOR" && return 0
    fi
    return 1
}

if PYTHON="$(find_floor)"; then
    echo "ci/setup.sh: using Python $FLOOR at $PYTHON"
elif [ -z "${CI:-}" ] && python3 -c "import sys; sys.exit(sys.version_info < tuple(map(int, '$FLOOR'.split('.'))))"; then
    PYTHON="$(command -v python3)"
    echo "ci/setup.sh: Python $FLOOR not found; using $("$PYTHON" --version) locally (CI runs the floor)"
else
    echo "ci/setup.sh: Python $FLOOR not found (looked for python$FLOOR and the runner tool cache; uv could not install it)" >&2
    exit 1
fi

"$PYTHON" -m venv --clear "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet pytest "coverage>=7.10" pyyaml
"$VENV/bin/python" --version

if BATS="$(command -v bats 2>/dev/null)"; then
    echo "ci/setup.sh: using bats at $BATS"
else
    if [ ! -x "$BATS_DIR/bin/bats" ]; then
        rm -rf "$BATS_DIR"
        if ! git -c advice.detachedHead=false clone --quiet --depth 1 --branch "v$BATS_VERSION" \
                https://github.com/bats-core/bats-core.git "$BATS_DIR" >&2 \
                || [ ! -x "$BATS_DIR/bin/bats" ]; then
            echo "ci/setup.sh: could not install bats-core v$BATS_VERSION into $BATS_DIR" >&2
            exit 1
        fi
    fi
    BATS="$BATS_DIR/bin/bats"
    echo "ci/setup.sh: using bats-core v$BATS_VERSION at $BATS"
fi
ln -sf "$BATS" "$VENV/bin/bats"
"$VENV/bin/bats" --version
