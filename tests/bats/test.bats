#!/usr/bin/env bats
# Tests of ci/test.sh: pytest under coverage, the 99% gate on the total and on
# each of git-semver and release, and the bats run.

load helpers

# The venv's interpreter. FAIL_PYTEST, FAIL_TOTAL and FAIL_FILE (a file name)
# make pytest, the total report or that file's report fail.
venv_python() {
    stub "$1" '
case "$*" in
    --version) echo "Python 3.10.99" ;;
    "-m coverage run -m pytest tests/ -v") [ -z "${FAIL_PYTEST:-}" ] || exit 1 ;;
    "-m coverage report --fail-under=99") [ -z "${FAIL_TOTAL:-}" ] || exit 2 ;;
    "-m coverage report --include="*)
        file="${4#--include=}"
        if [ "$file" = "${FAIL_FILE:-}" ]; then echo 95.0; exit 2; fi
        echo 100.0 ;;
esac
exit 0'
}

setup() {
    sandbox
    write_pyproject 3.10
    VENV="$XDG_CACHE_HOME/git-semver-ci/venv-3.10"
    venv_python "$VENV/bin/python"
    stub "$VENV/bin/bats" '[ -z "${FAIL_BATS:-}" ] || exit 1'
}

@test "runs pytest under coverage, the report, both per-file gates and bats" {
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 0 ]
    logged "python --version"
    logged "python -m coverage erase"
    logged "python -m coverage run -m pytest tests/ -v"
    logged "python -m coverage combine --quiet"
    logged "python -m coverage report --fail-under=99"
    logged "python -m coverage report --include=git-semver --format=total --fail-under=99"
    logged "python -m coverage report --include=release --format=total --fail-under=99"
    logged "bats tests/bats"
}

@test "fails when pytest fails, and still reports coverage and runs bats" {
    export FAIL_PYTEST=1
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
    logged "python -m coverage report --fail-under=99"
    logged "bats tests/bats"
}

@test "fails naming the gate when the total is below 99%" {
    export FAIL_TOTAL=1
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/test.sh: total line coverage is below 99%"* ]]
    logged "bats tests/bats"
}

@test "fails naming release and its figure when release is below 99%" {
    export FAIL_FILE=release
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/test.sh: release is at 95.0% line coverage, below 99%"* ]]
    [[ "$output" != *"git-semver is at"* ]]
}

@test "fails naming git-semver when git-semver is below 99%" {
    export FAIL_FILE=git-semver
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ci/test.sh: git-semver is at 95.0% line coverage, below 99%"* ]]
}

@test "fails when the bats tests fail" {
    export FAIL_BATS=1
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
}

@test "without setup, uses a python3 that has the test deps and a bats on PATH" {
    rm -rf "$VENV"
    venv_python python3
    stub bats
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 0 ]
    logged "python3 -m coverage run -m pytest tests/ -v"
    logged "bats tests/bats"
}

@test "without setup, fails with the setup hint when python3 lacks the test deps" {
    rm -rf "$VENV"
    stub python3 '[ "$1" = -c ] && exit 1; exit 0'
    stub bats
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"pytest, pyyaml or coverage 7.10+ is not installed; run: .vendored/pkg/git-cicd/git-cicd check --setup"* ]]
    not_logged "python3 -m coverage"
}

@test "fails with the setup hint when there is no bats" {
    rm "$VENV/bin/bats"
    run bash "$ROOT/ci/test.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"bats is not installed; run: .vendored/pkg/git-cicd/git-cicd check --setup"* ]]
    not_logged "python -m coverage"
}
