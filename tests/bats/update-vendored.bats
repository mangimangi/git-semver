#!/usr/bin/env bats
# Tests of ci/update-vendored.sh: the update-vendored job's inputs become
# .vendored/install arguments, and the token it gets.

load helpers

setup() {
    sandbox
    # python3 prints each argument on its own line, then the token.
    stub python3 '
printf "arg=%s\n" "$@"
printf "GH_TOKEN=%s\n" "$GH_TOKEN"'
}

@test "defaults to all vendors at the latest version" {
    run bash "$ROOT/ci/update-vendored.sh"
    [ "$status" -eq 0 ]
    logged "python3 .vendored/install all --version latest --pr --deps=install"
}

@test "passes the vendor and version inputs" {
    export CICD_INPUT_VENDOR=git-cicd CICD_INPUT_VERSION=0.0.5
    run bash "$ROOT/ci/update-vendored.sh"
    [ "$status" -eq 0 ]
    logged "python3 .vendored/install git-cicd --version 0.0.5 --pr --deps=install"
}

@test "empty inputs fall back to the defaults" {
    export CICD_INPUT_VENDOR= CICD_INPUT_VERSION= CICD_INPUT_PRIVATE=
    run bash "$ROOT/ci/update-vendored.sh"
    logged "python3 .vendored/install all --version latest --pr --deps=install"
}

@test "private=true adds --private" {
    export CICD_INPUT_PRIVATE=true
    run bash "$ROOT/ci/update-vendored.sh"
    logged "python3 .vendored/install all --version latest --pr --deps=install --private"
}

@test "private other than true adds nothing" {
    export CICD_INPUT_PRIVATE=false
    run bash "$ROOT/ci/update-vendored.sh"
    logged "python3 .vendored/install all --version latest --pr --deps=install"
    export CICD_INPUT_PRIVATE=yes
    run bash "$ROOT/ci/update-vendored.sh"
    [[ "$output" != *"arg=--private"* ]]
}

@test "an input is one argument and never run by a shell" {
    export CICD_INPUT_VENDOR='a b; touch pwned $(touch pwned2)'
    run bash "$ROOT/ci/update-vendored.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *'arg=a b; touch pwned $(touch pwned2)'$'\n''arg=--version'* ]]
    [ ! -e pwned ] && [ ! -e pwned2 ]
}

@test "GH_TOKEN is VENDOR_PAT when set" {
    export VENDOR_PAT=pat GITHUB_TOKEN=gt
    run bash "$ROOT/ci/update-vendored.sh"
    [[ "$output" == *"GH_TOKEN=pat"* ]]
}

@test "GH_TOKEN is GITHUB_TOKEN without VENDOR_PAT" {
    export GITHUB_TOKEN=gt
    run bash "$ROOT/ci/update-vendored.sh"
    [[ "$output" == *"GH_TOKEN=gt"* ]]
}

@test "GH_TOKEN is empty without either token" {
    run bash "$ROOT/ci/update-vendored.sh"
    [[ "$output" == *"GH_TOKEN="$'\n'* || "$output" == *"GH_TOKEN=" ]]
}

@test "exits with .vendored/install's status" {
    stub python3 'exit 3'
    run bash "$ROOT/ci/update-vendored.sh"
    [ "$status" -eq 3 ]
}
