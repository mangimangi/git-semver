#!/usr/bin/env bats
# Tests of ci/setup.sh: finding or installing the Python floor, the test venv,
# and bats.

load helpers

# A fake interpreter: `-m venv [--clear] DIR` makes DIR/bin/python another
# fake interpreter; `--version` prints a version; `-m pip install ... uv`
# drops a fake uv next to itself.
fake_python() {
    stub "$1" '
if [ "$1" = -m ] && [ "$2" = venv ]; then
    dir="${@: -1}"
    mkdir -p "$dir/bin"
    cp "$STUBS/.fakepy" "$dir/bin/python"
fi
if [ "$1" = --version ]; then echo "Python 3.11.99"; fi
if [ "$1" = -m ] && [ "$2" = pip ] && [ "${@: -1}" = uv ]; then
    cp "$STUBS/.fakeuv" "$(dirname "$0")/uv"
fi
exit 0'
}

setup() {
    sandbox
    write_pyproject 3.11
    fake_python "$STUBS/.fakepy"
    stub "$STUBS/.fakeuv" '
if [ "$1 $2" = "python find" ]; then echo "$STUBS/.uvpython"; fi
exit 0'
    fake_python "$STUBS/.uvpython"
    stub bats 'echo "Bats 9.9.9"'
    CACHE="$XDG_CACHE_HOME/git-semver-ci"
    VENV="$CACHE/venv-3.11"
}

@test "fails naming requires-python when pyproject.toml has no floor" {
    write_pyproject none
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *'cannot read requires-python (">=X.Y") from pyproject.toml'* ]]
}

@test "uses python<floor> from PATH and builds the venv with the test deps" {
    fake_python python3.11
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"using Python 3.11 at $STUBS/python3.11"* ]]
    logged "python3.11 -m venv --clear $VENV"
    logged ".fakepy -m pip install --quiet --upgrade pip"
    logged ".fakepy -m pip install --quiet pytest coverage>=7.10 pyyaml"
    logged ".fakepy --version"
}

@test "reads the floor from pyproject.toml rather than a fixed version" {
    write_pyproject 3.12
    fake_python python3.12
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    logged "python3.12 -m venv --clear $CACHE/venv-3.12"
}

@test "uses the runner tool cache when python<floor> is not on PATH" {
    fake_python "$RUNNER_TOOL_CACHE/Python/3.11.9/x64/bin/python3"
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"using Python 3.11 at $RUNNER_TOOL_CACHE/Python/3.11.9/x64/bin/python3"* ]]
    logged "python3 -m venv --clear $VENV"
}

@test "installs the floor with uv from PATH when no interpreter is found" {
    cp "$STUBS/.fakeuv" "$STUBS/uv"
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    logged ".fakeuv python install 3.11"
    logged ".fakeuv python find 3.11"
    [[ "$output" == *"using Python 3.11 at $STUBS/.uvpython"* ]]
    logged ".uvpython -m venv --clear $VENV"
}

@test "installs uv into a tools venv when uv is missing too" {
    fake_python python3
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    logged "python3 -m venv $CACHE/tools"
    logged ".fakepy -m pip install --quiet uv"
    [ -x "$CACHE/tools/bin/uv" ]
    [[ "$output" == *"using Python 3.11 at $STUBS/.uvpython"* ]]
}

@test "outside CI, falls back to a new enough python3 when the floor cannot be had" {
    # python3 can neither make the tools venv nor is it too old.
    stub python3 '
case "$1" in
    -c) exit 0 ;;
    --version) echo "Python 3.12.0" ;;
    -m) if [ "$2 $3" = "venv --clear" ]; then mkdir -p "$4/bin"; cp "$STUBS/.fakepy" "$4/bin/python"; else exit 1; fi ;;
esac'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Python 3.11 not found; using Python 3.12.0 locally (CI runs the floor)"* ]]
    logged "python3 -m venv --clear $VENV"
}

@test "outside CI, refuses a python3 older than the floor" {
    stub python3 '
case "$1" in
    -c) exit 1 ;;
    -m) exit 1 ;;
esac'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Python 3.11 not found (looked for python3.11 and the runner tool cache; uv could not install it)"* ]]
}

@test "in CI, fails rather than use another Python" {
    export CI=true
    stub python3 '
case "$1" in
    -c) exit 0 ;;
    -m) exit 1 ;;
esac'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Python 3.11 not found"* ]]
    not_logged "python3 -m venv --clear"
}

@test "links the bats on PATH into the venv" {
    fake_python python3.11
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"using bats at $STUBS/bats"* ]]
    [ "$(readlink "$VENV/bin/bats")" = "$STUBS/bats" ]
    logged "bats --version"
    not_logged "git "
}

@test "clones bats-core v1.11.1 into the cache when bats is missing" {
    fake_python python3.11
    rm "$STUBS/bats"
    stub git '
dest="${@: -1}"
mkdir -p "$dest/bin"
printf "#!/bin/sh\necho Bats 1.11.1\n" > "$dest/bin/bats"
chmod +x "$dest/bin/bats"'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    logged "git -c advice.detachedHead=false clone --quiet --depth 1 --branch v1.11.1 https://github.com/bats-core/bats-core.git $CACHE/bats-core-1.11.1"
    [ "$(readlink "$VENV/bin/bats")" = "$CACHE/bats-core-1.11.1/bin/bats" ]
    [[ "$output" == *"Bats 1.11.1"* ]]
}

@test "reuses a cached bats-core without cloning again" {
    fake_python python3.11
    rm "$STUBS/bats"
    stub "$CACHE/bats-core-1.11.1/bin/bats" 'echo "Bats 1.11.1"'
    stub git 'exit 1'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 0 ]
    not_logged "git "
    [ "$(readlink "$VENV/bin/bats")" = "$CACHE/bats-core-1.11.1/bin/bats" ]
}

@test "fails naming bats-core when it cannot be cloned" {
    fake_python python3.11
    rm "$STUBS/bats"
    stub git 'exit 128'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"could not install bats-core v1.11.1 into $CACHE/bats-core-1.11.1"* ]]
}

@test "fails when a clone leaves no bats executable" {
    fake_python python3.11
    rm "$STUBS/bats"
    stub git 'mkdir -p "${@: -1}"'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"could not install bats-core v1.11.1"* ]]
}
