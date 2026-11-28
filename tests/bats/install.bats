#!/usr/bin/env bats
# Tests of install.sh: what it downloads, from where, what it keeps, and the
# manifest it writes.

load helpers

# curl -fsSL URL -o DEST writes "curl:URL" (a workflow template gets an
# __INSTALL_DIR__ placeholder); a URL matching $CURL_FAIL fails.
# gh api repos/R/contents/P?ref=REF --jq .content prints "gh:P@REF", base64.
setup() {
    sandbox
    stub curl '
url="$2"; dest="$4"
if [ -n "${CURL_FAIL:-}" ] && [[ "$url" == *$CURL_FAIL* ]]; then exit 22; fi
case "$url" in
    */templates/github/workflows/*) printf "run: __INSTALL_DIR__/release\n" > "$dest" ;;
    *) printf "curl:%s\n" "$url" > "$dest" ;;
esac'
    export VENDOR_INSTALL_DIR=.vendored/pkg/git-semver
}

gh_stub() {
    stub gh '
path="${2#repos/*/contents/}"
printf "gh:%s\n" "$path" | base64'
}

RAW=https://raw.githubusercontent.com/mangimangi/git-semver

@test "fails with usage when no version is given" {
    run bash "$ROOT/install.sh"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage: install.sh <version>"* ]]
}

@test "fails when VENDOR_INSTALL_DIR is not set" {
    unset VENDOR_INSTALL_DIR
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -ne 0 ]
    [[ "$output" == *"VENDOR_INSTALL_DIR is required"* ]]
}

@test "installs git-semver and release, executable, from the version's tag" {
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [[ "$output" == *"Installing git-semver v1.2.3 from mangimangi/git-semver"* ]]
    [ "$(cat .vendored/pkg/git-semver/git-semver)" = "curl:$RAW/v1.2.3/git-semver" ]
    [ "$(cat .vendored/pkg/git-semver/release)" = "curl:$RAW/v1.2.3/release" ]
    [ -x .vendored/pkg/git-semver/git-semver ] && [ -x .vendored/pkg/git-semver/release ]
    [[ "$output" == *"Done! git-semver v1.2.3 installed."* ]]
}

@test "VENDOR_REF wins over the argument and loses its v prefix" {
    export VENDOR_REF=v2.0.0
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ "$(cat .vendored/pkg/git-semver/release)" = "curl:$RAW/v2.0.0/release" ]
}

@test "a v prefix on the argument is stripped" {
    run bash "$ROOT/install.sh" v1.2.3
    [[ "$output" == *"Installing git-semver v1.2.3 from"* ]]
}

@test "VENDOR_REPO picks the source repository" {
    export VENDOR_REPO=someone/fork
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat .vendored/pkg/git-semver/git-semver)" = "curl:https://raw.githubusercontent.com/someone/fork/v1.2.3/git-semver" ]
}

@test "downloads with gh api when GH_TOKEN is set and gh exists" {
    gh_stub
    export GH_TOKEN=t
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    logged "gh api repos/mangimangi/git-semver/contents/git-semver?ref=v1.2.3 --jq .content"
    [ "$(cat .vendored/pkg/git-semver/git-semver)" = "gh:git-semver?ref=v1.2.3" ]
    not_logged "curl "
}

@test "falls back to curl when GH_TOKEN is set but gh is missing" {
    export GH_TOKEN=t
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ "$(cat .vendored/pkg/git-semver/git-semver)" = "curl:$RAW/v1.2.3/git-semver" ]
}

@test "uses curl when gh exists but GH_TOKEN is not set" {
    gh_stub
    run bash "$ROOT/install.sh" 1.2.3
    not_logged "gh "
}

@test "removes scripts left by older versions" {
    mkdir -p .vendored/pkg/git-semver
    touch .vendored/pkg/git-semver/bump-and-release .vendored/pkg/git-semver/semver
    run bash "$ROOT/install.sh" 1.2.3
    [ ! -e .vendored/pkg/git-semver/bump-and-release ]
    [ ! -e .vendored/pkg/git-semver/semver ]
}

@test "creates the config from the template when it is missing" {
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat .vendored/configs/git-semver.json)" = "curl:$RAW/v1.2.3/templates/semver/config.json" ]
    [[ "$output" == *"Created .vendored/configs/git-semver.json"* ]]
}

@test "keeps an existing config" {
    mkdir -p .vendored/configs
    echo '{"mine": true}' > .vendored/configs/git-semver.json
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat .vendored/configs/git-semver.json)" = '{"mine": true}' ]
    [[ "$output" != *"Created .vendored/configs"* ]]
}

@test "installs the config schema into the manifests" {
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat .vendored/manifests/git-semver.schema)" = "curl:$RAW/v1.2.3/templates/config.schema" ]
}

@test "installs version-bump.yml with the install directory filled in" {
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat .github/workflows/version-bump.yml)" = "run: .vendored/pkg/git-semver/release" ]
    [[ "$output" == *"Installed .github/workflows/version-bump.yml"* ]]
}

@test "keeps an existing version-bump.yml" {
    mkdir -p .github/workflows
    echo mine > .github/workflows/version-bump.yml
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ "$(cat .github/workflows/version-bump.yml)" = mine ]
    [[ "$output" == *"Workflow .github/workflows/version-bump.yml already exists, skipping"* ]]
}

@test "a workflow template that cannot be downloaded is skipped, not fatal" {
    export CURL_FAIL=templates/github/workflows
    export VENDOR_MANIFEST="$BATS_TEST_TMPDIR/manifest"
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [[ "$output" != *"Installed .github/workflows"* ]]
    [ ! -e .github/workflows/version-bump.yml ]
    ! grep -q version-bump "$VENDOR_MANIFEST"
}

@test "a gh download of a missing template leaves no empty workflow behind" {
    stub gh '
case "$2" in */templates/github/workflows/*) exit 1 ;; esac
printf "gh:%s\n" "${2#repos/*/contents/}" | base64'
    export GH_TOKEN=t
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ ! -e .github/workflows/version-bump.yml ]
}

# An upgrade: an earlier git-semver install is recorded in the repository.
@test "an upgrade recorded by the version manifest does not add version-bump.yml" {
    mkdir -p .vendored/manifests
    echo 0.0.15 > .vendored/manifests/git-semver.version
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ ! -e .github/workflows/version-bump.yml ]
    [[ "$output" == *"Not installing .github/workflows/version-bump.yml: an upgrade never adds it"* ]]
    not_logged "curl -fsSL $RAW/v1.2.3/templates/github/workflows"
}

@test "an upgrade recorded by the files manifest does not add version-bump.yml" {
    mkdir -p .vendored/manifests
    printf '.vendored/pkg/git-semver/git-semver\n' > .vendored/manifests/git-semver.files
    run bash "$ROOT/install.sh" 1.2.3
    [ ! -e .github/workflows/version-bump.yml ]
}

@test "an upgrade over installed scripts does not add version-bump.yml" {
    mkdir -p .vendored/pkg/git-semver
    touch .vendored/pkg/git-semver/git-semver
    run bash "$ROOT/install.sh" 1.2.3
    [ ! -e .github/workflows/version-bump.yml ]
}

@test "an upgrade from the legacy .semver layout does not add version-bump.yml" {
    mkdir -p .semver
    touch .semver/git-semver
    run bash "$ROOT/install.sh" 1.2.3
    [ ! -e .github/workflows/version-bump.yml ]
}

@test "the manifest of an upgrade lists no workflow that is not there" {
    mkdir -p .vendored/manifests
    printf '.vendored/pkg/git-semver/git-semver\n.github/workflows/version-bump.yml\n' \
        > .vendored/manifests/git-semver.files
    export VENDOR_MANIFEST=.vendored/manifests/git-semver.files
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ "$(cat "$VENDOR_MANIFEST")" = ".vendored/pkg/git-semver/git-semver
.vendored/pkg/git-semver/release
.vendored/manifests/git-semver.schema" ]
}

@test "the manifest keeps a workflow an earlier install wrote and left in place" {
    mkdir -p .vendored/manifests .github/workflows
    echo mine > .github/workflows/version-bump.yml
    printf '.vendored/pkg/git-semver/git-semver\n.github/workflows/version-bump.yml\n' \
        > .vendored/manifests/git-semver.files
    export VENDOR_MANIFEST=.vendored/manifests/git-semver.files
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat .github/workflows/version-bump.yml)" = mine ]
    [ "$(cat "$VENDOR_MANIFEST")" = ".vendored/pkg/git-semver/git-semver
.vendored/pkg/git-semver/release
.vendored/manifests/git-semver.schema
.github/workflows/version-bump.yml" ]
}

# A first install into a repository that releases through git-cicd.
write_cicd() {
    mkdir -p .vendored/configs
    printf '%s\n' "$1" > .vendored/configs/git-cicd.json
}

@test "a first install whose git-cicd config runs release does not add the workflow and says why" {
    write_cicd '{
  "jobs": {
    "test": {"on": ["open"], "paths": ["release"], "steps": [["git-semver", "check-bump"]]},
    "release": {
      "on": ["merge"],
      "steps": [
        "release"
      ]
    }
  }
}'
    export VENDOR_MANIFEST="$BATS_TEST_TMPDIR/manifest"
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ ! -e .github/workflows/version-bump.yml ]
    [ "$(grep -c "Not installing" <<<"$output")" -eq 1 ]
    [[ "$output" == *"Not installing .github/workflows/version-bump.yml: the repository releases through git-cicd (.vendored/configs/git-cicd.json has a job step that runs git-semver's release)"* ]]
    ! grep -q version-bump "$VENDOR_MANIFEST"
}

@test "a git-cicd step running the installed release, as a command with arguments, counts" {
    write_cicd '{"jobs": {"r": {"steps": ["ci/test.sh", [".vendored/pkg/git-semver/release", "--dry"]]}}}'
    run bash "$ROOT/install.sh" 1.2.3
    [ ! -e .github/workflows/version-bump.yml ]
    [[ "$output" == *"releases through git-cicd"* ]]
}

@test "a git-cicd config that does not run release still gets the workflow" {
    write_cicd '{"jobs": {"release": {"paths": ["release"], "steps": [["sh", "release"], "ci/release.sh"]}}}'
    run bash "$ROOT/install.sh" 1.2.3
    [ -e .github/workflows/version-bump.yml ]
    [[ "$output" == *"Installed .github/workflows/version-bump.yml"* ]]
}

@test "a first install whose git-semver config bumps in the pull request does not add the workflow" {
    mkdir -p .vendored/configs
    printf '{\n  "bump_on": "pull_request"\n}\n' > .vendored/configs/git-semver.json
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ ! -e .github/workflows/version-bump.yml ]
    [[ "$output" == *'releases through git-cicd (.vendored/configs/git-semver.json sets "bump_on": "pull_request")'* ]]
}

@test "bump_on merge in the git-semver config still gets the workflow" {
    mkdir -p .vendored/configs
    echo '{"bump_on": "merge"}' > .vendored/configs/git-semver.json
    run bash "$ROOT/install.sh" 1.2.3
    [ -e .github/workflows/version-bump.yml ]
}

@test "a core script that cannot be downloaded fails the install" {
    export CURL_FAIL=/release
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -ne 0 ]
    [[ "$output" != *"Done!"* ]]
}

@test "writes the manifest of installed files when VENDOR_MANIFEST is set" {
    export VENDOR_MANIFEST="$BATS_TEST_TMPDIR/manifest"
    run bash "$ROOT/install.sh" 1.2.3
    [ "$status" -eq 0 ]
    [ "$(cat "$VENDOR_MANIFEST")" = ".vendored/pkg/git-semver/git-semver
.vendored/pkg/git-semver/release
.vendored/manifests/git-semver.schema
.github/workflows/version-bump.yml" ]
}

@test "the manifest leaves out a workflow it did not install" {
    mkdir -p .github/workflows
    echo mine > .github/workflows/version-bump.yml
    export VENDOR_MANIFEST="$BATS_TEST_TMPDIR/manifest"
    run bash "$ROOT/install.sh" 1.2.3
    [ "$(cat "$VENDOR_MANIFEST")" = ".vendored/pkg/git-semver/git-semver
.vendored/pkg/git-semver/release
.vendored/manifests/git-semver.schema" ]
}

@test "writes no manifest when VENDOR_MANIFEST is not set" {
    run bash "$ROOT/install.sh" 1.2.3
    [ ! -e manifest ] && [ -z "$(ls "$BATS_TEST_TMPDIR" | grep -x manifest)" ]
}
