# Adopt git-vendored Framework Features

Plan for git-semver to adopt three framework features described in the
git-vendored vendor adoption guide. Assumes the framework provides each
feature; git-semver is the consumer.

---

## 1. `$VENDOR_LIB` — Use Framework Shell Helpers in `install.sh`

### Current state

`install.sh` defines its own `fetch_file()` (lines 28-39) with a custom
signature:

```bash
fetch_file <repo_path> <dest> [<ref>]
```

It handles `GH_TOKEN` / `gh api` auth inline and does `chmod +x` separately
after each call.

### Target state

Source the framework's helper library with an inline fallback so install.sh
works with both new and old framework versions:

```bash
source "$VENDOR_LIB" 2>/dev/null || {
    fetch_file() {
        local src="$1" dst="$2"
        curl -fsSL "https://raw.githubusercontent.com/$VENDOR_REPO/$VENDOR_REF/$src" -o "$dst"
        [ "${3:-}" = "+x" ] && chmod +x "$dst"
        echo "$dst" >> "${VENDOR_MANIFEST:-/dev/null}"
    }
}
```

### Changes required

1. **Replace `fetch_file` definition** with `source "$VENDOR_LIB"` + inline
   fallback block.
2. **Adapt call sites** to the new signature `fetch_file <repo_path> <local_path> [+x]`:
   - `fetch_file "git-semver" "$INSTALL_DIR/git-semver" "+x"` (was separate `chmod +x`)
   - `fetch_file "bump-and-release" "$INSTALL_DIR/bump-and-release" "+x"`
   - `fetch_file "templates/semver/config.json" ".vendored/configs/git-semver.json"`
   - `fetch_file "templates/github/workflows/version-bump.yml" ".github/workflows/$workflow"`
3. **Remove manual manifest writes** — `fetch_file` now appends to
   `$VENDOR_MANIFEST` automatically. Drop the `INSTALLED_FILES` array and the
   trailing `printf '%s\n' "${INSTALLED_FILES[@]}" > "$VENDOR_MANIFEST"` block.
4. **Remove manual `mkdir -p`** for parent directories — the framework's
   `fetch_file` creates parent dirs. Keep `mkdir -p` only for directories that
   aren't created as a side effect (e.g., `.vendored/configs` if the first
   `fetch_file` targets a file there, it's handled; but `.github/workflows`
   may still need explicit creation if the workflow install is conditional).
5. **Drop `$SEMVER_REPO` local alias** — use `$VENDOR_REPO` directly (already
   set by the framework; fallback is in the `source` block which sets
   `$VENDOR_REPO` if needed).

### Backwards compatibility

The inline fallback handles the case where `$VENDOR_LIB` is not set (old
framework or dogfood self-install). The fallback `fetch_file` uses
`$VENDOR_REPO` and `$VENDOR_REF` which are already required by install.sh.

Auth: the fallback uses plain `curl` (public repo). The framework's
`fetch_file` handles `$VENDOR_PAT` / `$GH_TOKEN` for private repos — no
changes needed on git-semver side.

### Test considerations

- `test_install.py` tests the install script — update mocks/expectations for
  new `fetch_file` signature.
- Test both paths: with `$VENDOR_LIB` set (mocked) and without (fallback).

---

## 2. Vendor Support Config

### Current state

`.vendored/configs/git-semver.json` has a `_vendor` key with `repo`,
`install_branch`, `protected`, `allowed`. No `support` key.

### Target state

Add `support` to the `_vendor` block:

```json
{
  "_vendor": {
    "repo": "mangimangi/git-semver",
    "install_branch": "chore/install-git-semver",
    "protected": [".semver/**", ".github/workflows/version-bump.yml"],
    "allowed": [".vendored/configs/git-semver.json"],
    "support": {
      "issues": "https://github.com/mangimangi/git-semver/issues",
      "instructions": "Include your .vendored/manifests/git-semver.version and .vendored/configs/git-semver.json in bug reports.",
      "labels": ["vendored", "bug"]
    }
  },
  "version_file": "VERSION",
  "files": ["git-semver", "bump-and-release", "install.sh", "templates/github/workflows/version-bump.yml", "templates/AGENTS.md", "templates/semver/config.json"],
  "changelog": true
}
```

### Changes required

1. **Add `support` key** inside `_vendor` in `.vendored/configs/git-semver.json`.
2. **Update `templates/semver/config.json`** to include a placeholder `support`
   block so new adopters of git-semver get the schema by default.

### Notes

- `issues` could be omitted (framework derives it from `repo`), but being
  explicit is clearer.
- `instructions` should mention the version manifest and config file since
  those are the most useful debugging artifacts.
- No code changes to `git-semver` or `bump-and-release` — this is config-only.

---

## 3. Codex Compatibility

### Current state

git-semver does not ship vendor hooks (no `.vendored/pkg/git-semver/hooks/`
directory). It has no session scripts that reference `$CLAUDE_PROJECT_DIR`.

The files that *do* reference `$CLAUDE_PROJECT_DIR` are framework-owned:
- `.claude/settings.json` — orchestrator entry point (framework-owned)
- `.claude/hooks/vendored-session.sh` — session orchestrator (framework-owned)

### Assessment

**No changes required on git-semver side for Codex compatibility.**

- git-semver has no hook scripts → nothing to migrate from
  `$CLAUDE_PROJECT_DIR` to `$PROJECT_DIR`.
- The orchestrator and `.claude/settings.json` are framework-owned → the
  framework's `--setup-hooks` command handles creating/updating these for both
  Claude and Codex.
- git-semver doesn't ship its own orchestrator → already compliant with
  "let the framework invoke them" guidance.

### If git-semver adds hooks in the future

Place them at `.vendored/pkg/git-semver/hooks/` and use:

```bash
PROJECT_DIR="${PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
```

Never reference `$CLAUDE_PROJECT_DIR`.

---

## Summary

| Feature            | Scope                 | Files changed                                            |
|--------------------|-----------------------|----------------------------------------------------------|
| `$VENDOR_LIB`     | install.sh refactor   | `install.sh`, `tests/test_install.py`                    |
| Support config     | config-only           | `.vendored/configs/git-semver.json`, `templates/semver/config.json` |
| Codex compat       | **no changes needed** | —                                                        |

### Dependencies

- Feature 1 depends on the framework shipping `$VENDOR_LIB` (the shell helper
  library). Until then, the inline fallback is the only active code path, which
  means the refactor can land now and "activate" later when the framework
  catches up.
- Feature 2 depends on the framework supporting the `support` schema in its
  config reader / `feedback` command. Adding the config key now is harmless
  (unknown keys are ignored).
- Feature 3 has no dependency — git-semver is already compliant.

### Ordering

Features 1 and 2 are independent and can be done in parallel. Feature 3
requires no work.
