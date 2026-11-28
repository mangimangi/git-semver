#!/usr/bin/env bats
# The sandbox guards: sandbox removes every token a test could pick up from the
# runner, so none can reach a test's output, and hides the runner's own
# interpreters, tools and tool cache, so no test depends on which of them the
# machine has.

load helpers

@test "sandbox unsets every token exported before it" {
    export CICD_WRITE_TOKEN=ghp_FAKEwrite0123456789abcdefABCDEF0123
    export CICD_READ_TOKEN=ghp_FAKEread0123456789abcdefABCDEF01234
    export VENDOR_PAT=github_pat_FAKE0123456789abcdefABCDEF
    export GH_TOKEN=gho_FAKE0123456789abcdefABCDEF012345678
    export GITHUB_TOKEN=ghs_FAKE0123456789abcdefABCDEF01234567
    sandbox
    local name
    for name in CICD_WRITE_TOKEN CICD_READ_TOKEN VENDOR_PAT GH_TOKEN GITHUB_TOKEN; do
        [ -z "${!name+set}" ] || { echo "$name is still set"; return 1; }
    done
    run env
    [[ "$output" != *FAKE* ]]
}

# A machine with every Python: a python3.11, a python3 and uv on PATH, and the
# runner tool cache holding a 3.11, all set before sandbox runs.
host_with_every_python() {
    local host="$BATS_TEST_TMPDIR/host" name
    mkdir -p "$host/bin" "$host/toolcache/Python/3.11.9/x64/bin"
    for name in python3.11 python3.12 python3 uv gh git bats curl; do
        printf '#!/bin/sh\necho "host %s $*"\n' "$name" > "$host/bin/$name"
        chmod +x "$host/bin/$name"
    done
    cp "$host/bin/python3" "$host/toolcache/Python/3.11.9/x64/bin/python3"
    export PATH="$host/bin:$PATH"
    export RUNNER_TOOL_CACHE="$host/toolcache"
}

@test "sandbox hides the host's interpreters and tools" {
    host_with_every_python
    sandbox
    local name
    for name in python3.11 python3.12 python3 uv gh git bats curl; do
        ! command -v "$name" || { echo "$name is visible"; return 1; }
    done
}

@test "sandbox points the runner tool cache at an empty directory of the test's own" {
    host_with_every_python
    sandbox
    [ "$RUNNER_TOOL_CACHE" = "$BATS_TEST_TMPDIR/toolcache" ]
    [ -d "$RUNNER_TOOL_CACHE" ]
    [ -z "$(ls -A "$RUNNER_TOOL_CACHE")" ]
}

@test "ci/setup.sh does not find the floor on a host that has every Python" {
    host_with_every_python
    sandbox
    write_pyproject 3.11
    stub python3 'exit 1'
    run bash "$ROOT/ci/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Python 3.11 not found (looked for python3.11 and the runner tool cache; uv could not install it)"* ]]
    [[ "$output" != *host* ]]
}
