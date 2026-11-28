# tests/bats/helpers.bash - shared setup for the bats tests of the shell
# scripts (install.sh and ci/*.sh).
#
# Each test runs in its own sandbox: a work directory, a HOME and cache under
# BATS_TEST_TMPDIR, and a PATH made of two directories only - $STUBS (fake
# commands a test writes with `stub`) and $SYSBIN (links to the few real tools
# the scripts use). Nothing else on the machine (python, uv, git, gh, curl,
# bats) is visible unless a test stubs it, so every case is decided by the
# test, not by what the runner happens to have installed.

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

SYSTEM_TOOLS=(bash sed head mkdir rm ln cat chmod mktemp mv cp base64 dirname
              basename tr grep env sort ls touch readlink)

# Tokens no test may read from the runner. guard.bats fails without the
# unset in sandbox.
TOKENS=(CICD_WRITE_TOKEN CICD_READ_TOKEN VENDOR_PAT GH_TOKEN GITHUB_TOKEN)

sandbox() {
    WORK="$BATS_TEST_TMPDIR/work"
    STUBS="$BATS_TEST_TMPDIR/stubs"
    # Outside the test's own directory: bats removes that with this PATH.
    SYSBIN="$BATS_RUN_TMPDIR/sysbin"
    STUB_LOG="$BATS_TEST_TMPDIR/stub.log"
    mkdir -p "$WORK" "$STUBS" "$SYSBIN"
    : > "$STUB_LOG"
    local tool real
    for tool in "${SYSTEM_TOOLS[@]}"; do
        # From the system directories, not wrappers earlier on the caller's PATH.
        real="$(PATH=/usr/local/bin:/usr/bin:/bin command -v "$tool")"
        ln -sf "$real" "$SYSBIN/$tool"
    done
    export STUB_LOG STUBS
    export HOME="$BATS_TEST_TMPDIR/home"
    export XDG_CACHE_HOME="$BATS_TEST_TMPDIR/cache"
    export PATH="$STUBS:$SYSBIN"
    mkdir -p "$HOME"
    # The token guard: no test sees a real token (TOKENS, below).
    unset "${TOKENS[@]}"
    unset CI RUNNER_TOOL_CACHE \
          VENDOR_REF VENDOR_REPO VENDOR_INSTALL_DIR VENDOR_MANIFEST \
          CICD_INPUT_VENDOR CICD_INPUT_VERSION CICD_INPUT_PRIVATE
    cd "$WORK"
}

# stub NAME [BODY] - write an executable $STUBS/NAME (or the path NAME when
# it contains a slash) that appends "NAME args..." to $STUB_LOG, then runs
# BODY (bash, with the arguments in "$@").
stub() {
    local name="$1" body="${2:-}" path
    case "$name" in
        */*) path="$name"; mkdir -p "$(dirname "$path")" ;;
        *) path="$STUBS/$name" ;;
    esac
    {
        printf '#!%s\n' "$(command -v bash)"
        printf 'printf "%%s\\n" "%s $*" >> "$STUB_LOG"\n' "$(basename "$name")"
        printf '%s\n' "$body"
    } > "$path"
    chmod +x "$path"
}

# logged LINE - succeed when $STUB_LOG has exactly LINE.
logged() {
    grep -qxF -- "$1" "$STUB_LOG" || {
        echo "expected in stub log: $1" >&2
        echo "stub log:" >&2
        cat "$STUB_LOG" >&2
        return 1
    }
}

# not_logged PATTERN - succeed when no $STUB_LOG line starts with PATTERN.
not_logged() {
    if grep -q -- "^$1" "$STUB_LOG"; then
        echo "unexpected in stub log: $1" >&2
        cat "$STUB_LOG" >&2
        return 1
    fi
}

# write_pyproject [FLOOR] - a pyproject.toml naming FLOOR (default 3.10) as
# the requires-python floor; with FLOOR "none", one without requires-python.
write_pyproject() {
    local floor="${1:-3.10}"
    if [ "$floor" = none ]; then
        printf '[project]\nname = "x"\n' > pyproject.toml
    else
        printf '[project]\nname = "x"\nrequires-python = ">=%s"\n' "$floor" > pyproject.toml
    fi
}
