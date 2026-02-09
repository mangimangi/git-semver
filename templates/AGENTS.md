# git-semver — AI Agent Instructions

This project uses **git-semver** for automatic semantic versioning. Configuration lives in `.semver/config.json`.

## File Permissions

> **NEVER edit installed files directly.** Update via the install workflow or
> by re-running `install.sh`. Installed copies are overwritten on every update.

| Installed path | Edit? | Notes |
|---------------|-------|-------|
| `.semver/git-semver` | **NO** | Core script — update via install-vendored |
| `.github/workflows/version-bump.yml` | **NO** | Installed workflow |
| `.semver/config.json` | **YES** | Your versioning config |
| `.semver/.version` | **NO** | Auto-managed version tracker |
| `.vendored/install` | **NO** | Vendor install script — update via install-vendored |
| `.vendored/check` | **NO** | Vendor protection script — update via install-vendored |
| `.vendored/config.json` | **YES** | Vendor registry — add/configure vendors here |
| `.vendored/.version` | **NO** | Auto-managed version tracker |
| `.dogfood/resolve` | **NO** | Dogfood resolver — update via install-vendored |
| `.github/workflows/install-vendored.yml` | **NO** | Installed workflow |
| `.github/workflows/check-vendor.yml` | **NO** | Installed workflow |
| `.github/workflows/dogfood.yml` | **NO** | Installed workflow |

## Quick Reference

```bash
# Check current version
.semver/git-semver version
.semver/git-semver version --subdir frontend

# Check if a bump is needed (exit 0 = yes, 1 = no)
.semver/git-semver check --since HEAD~1
.semver/git-semver check --since HEAD~1 --subdir frontend

# Bump version locally (patch/minor/major)
.semver/git-semver bump patch
.semver/git-semver bump minor --no-push
.semver/git-semver bump major --no-push --description "Breaking change description"
.semver/git-semver bump patch --subdir frontend

# Check all components and bump triggered ones (used by CI)
.semver/git-semver bump-all --since HEAD~5
```

## How Versioning Works

1. **On merge to main**: `version-bump.yml` runs `git-semver bump-all` to check all components (root + subdirectories) against files changed in the push
2. **If matched**: bumps automatically — updates version files, configured files, changelogs, commits, tags, and pushes
3. **Manual releases**: trigger `version-bump.yml` via workflow_dispatch for minor/major bumps (with optional subdirectory selector)

### What triggers a bump

The `files` patterns in `.semver/config.json` determine which file changes trigger an automatic patch bump. Only patches are automatic — minor and major bumps are always manual.

### Commit conventions

These commit prefixes have special meaning:

| Prefix | Purpose |
|--------|---------|
| `chore: bump version` | Version bump commit — skipped by version-bump.yml |
| `chore: install` | Install PR commits — skipped by version-bump.yml |

Do not use these prefixes for regular work — they cause version-bump.yml to skip the commit.

## Configuration

Edit `.semver/config.json` to control versioning:

```json
{
  "version_file": "VERSION",
  "files": ["src/**/*.py"],
  "updates": {
    "VERSION": "file",
    "src/version.py": ["VERSION = "]
  },
  "changelog": {
    "file": "CHANGELOG.md",
    "ignore_prefixes": ["chore:", "docs:"]
  }
}
```

- **`files`**: glob patterns for files that trigger automatic patch bumps
- **`updates`**: files to update with the new version string on bump
- **`changelog`**: changelog generation settings (set to `false` to disable)
- **Subdirectory keys**: any non-reserved top-level key with a dict value is a subdirectory config (for monorepo support). Tags become `<subdir>/vX.Y.Z`.

See the [git-semver README](https://github.com/USER/git-semver#configuration) for the full config reference.
