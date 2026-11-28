#!/usr/bin/env bats
# The token guard: sandbox removes every token a test could pick up from the
# runner, so none can reach a test's output.

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
