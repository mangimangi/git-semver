# git-semver

Config-driven semantic versioning for git repos. Declare which files matter, get automatic patch bumps on merge. Zero dependencies beyond Python 3 and git.

## Features

- **File-driven, not commit-driven** — declare which file changes constitute a release, no commit conventions required
- **Single script** — one Python file, zero dependencies
- **Config-driven** — `.semver/config.json` controls everything
- **Automatic patch bumps** — on merge to main when configured files change
- **Manual minor/major** — deliberate releases via `workflow_dispatch`
- **Changelog generation** — from commit messages, with configurable noise filters
- **No PAT required** — core versioning uses `GITHUB_TOKEN`
- **CI-agnostic core** — the script works anywhere git and Python 3 are available

## Installation

### Via curl (initial install)

```bash
curl -fsSL https://raw.githubusercontent.com/USER/git-semver/latest/install.sh | bash -s <version> <repo>
```

### Via GitHub Actions (ongoing updates)

The `install-git-semver.yml` workflow handles both initial installation and updates:
- Runs weekly to check for updates (configurable schedule)
- Can be triggered manually from the Actions tab with an optional version
- Creates a PR when updates are available

### What gets installed

```
your-project/
├── .semver/
│   ├── git-semver         # Core script (don't edit)
│   ├── config.json        # Your config (edit this!)
│   └── .version           # Installed version tracker
└── .github/
    └── workflows/
        ├── version-bump.yml          # Auto-bump on merge
        ├── is-version-bump.yml       # Reusable: detect bump commits
        └── install-git-semver.yml    # Self-update workflow
```

## Quick Start

```bash
# 1. Install git-semver (creates .semver/ and workflow files)

# 2. Configure .semver/config.json
cat > .semver/config.json << 'EOF'
{
  "version_file": "VERSION",
  "files": [
    "src/**/*.py",
    "lib/*.js"
  ],
  "updates": {
    "VERSION": "file",
    "src/version.py": ["VERSION = "]
  },
  "changelog": true
}
EOF

# 3. Create a VERSION file
echo "0.1.0" > VERSION

# 4. Commit and push — version-bump.yml handles the rest
```

## Commands

```
git-semver version                          # Print current version
git-semver check [--since <commit>]         # Check if a bump is needed (exit 0=yes, 1=no)
git-semver bump [patch|minor|major] [opts]  # Bump version, commit, tag, push
```

### `git-semver version`

Reads `version_file` from `.semver/config.json` and prints the current version.

### `git-semver check [--since <commit>]`

Diffs changed files since the given commit (or `HEAD~1` if omitted) against the `files` patterns in config. Exit 0 = bump needed, exit 1 = no bump needed. Outputs matched files and patterns to stdout.

### `git-semver bump [patch|minor|major]`

The complete version release operation:

1. Reads current version from `version_file`
2. Computes new version (default: `patch`)
3. Writes new version to `version_file`
4. Applies `updates` — pattern-based find-and-replace across configured files
5. Updates changelog (if enabled) — collects commits since last tag, filters noise prefixes, prepends dated entry
6. Commits as `chore: bump version to vX.Y.Z`
7. Creates annotated tag `vX.Y.Z` + updates `latest` tag
8. Pushes commit and tags

Flags peel back layers:

| Flag | Behavior |
|------|----------|
| (default) | update files, commit, tag, push |
| `--no-push` | update files, commit, tag |
| `--no-commit` | update files only |
| `--description "..."` | Override auto-collected changelog with a curated description |

### Local usage

```bash
# Bump patch locally (useful for testing or non-CI workflows)
./git-semver bump patch

# Check if files changed since a specific commit
./git-semver check --since abc123

# Bump without pushing (review before push)
./git-semver bump minor --no-push
```

## Configuration

### `.semver/config.json`

```json
{
  "version_file": "VERSION",
  "files": [
    "src/**/*.py",
    "lib/*.js",
    "templates/**/*"
  ],
  "updates": {
    "VERSION": "file",
    "src/version.py": ["VERSION = "]
  },
  "changelog": {
    "file": "CHANGELOG.md",
    "ignore_prefixes": ["chore:", "docs:"]
  },
  "install": {
    "on_merge": true,
    "automerge_version_bumps": true,
    "schedule": "0 9 * * 1"
  }
}
```

### Keys

**`version_file`** (default: `"VERSION"`)

Path to the file holding the current version string. Read before a bump, written with the new version after. Does not need to appear in `files` or `updates` — it is managed implicitly.

**`files`** (required)

Glob patterns for files whose changes trigger an automatic **patch** bump on merge to main. Supports `*`, `**`, and `?` patterns. Only patches are automatic — minor and major bumps are always manual via `workflow_dispatch`.

**`updates`** (required)

Map of files to update with the new version string when a bump occurs. Two action types:

| Action | Format | Example |
|--------|--------|---------|
| `"file"` | Write entire file as version + newline | `"VERSION": "file"` |
| `["pattern", ...]` | Regex find-and-replace | `"src/lib.py": ["VERSION = "]` |

Pattern matching for updates:
- Pattern containing `=`: matches `pattern + quoted_version`, replaces with `pattern + "new_version"` (preserves quote style)
- Pattern without `=`: matches `pattern + version`, replaces with `pattern + new_version`

**`changelog`** (default: enabled)

| Value | Behavior |
|-------|----------|
| absent / `true` | Enabled, defaults: `CHANGELOG.md`, no ignore prefixes |
| `false` | Disabled entirely |
| `{ "file": "...", "ignore_prefixes": [...] }` | Custom file path and/or commit prefix filters |

When enabled, collects commit messages since the last tag, filters out noise prefixes, and prepends a dated entry under `## [version] - date`.

**`install`** — controls installed workflow behavior:

| Key | Default | Description |
|-----|---------|-------------|
| `on_merge` | `true` | Auto-trigger patch bump when `files` change on merge to main. When `false`, bumps are manual-only |
| `automerge_version_bumps` | `true` | Version bump commits push directly to main. When `false`, creates a PR instead |
| `schedule` | `"0 9 * * 1"` | Cron for `install-git-semver.yml` update checks. Set to `false` to disable |

## GitHub Actions

### version-bump.yml

Thin wrapper around `git-semver` — handles triggers and auth, the script handles everything else.

- **Push trigger**: on merge to main/master. Skips automated commits (`chore: bump version`, `chore: install`). Runs `git-semver check` to see if changed files match patterns. Respects `install.on_merge` config.
- **Manual trigger**: `workflow_dispatch` with `bump_type` and optional `changelog_description`. Always bumps (skips the check).
- **Auto bumps are patches only.** Minor and major require manual dispatch.
- **Direct push mode** (default): `git-semver bump` pushes directly to main.
- **PR mode**: when `automerge_version_bumps: false`, creates a branch and PR instead.

### is-version-bump.yml

Reusable workflow. Returns `is_version_bump: true|false` based on commit message prefix `chore: bump version`. Pure shell — no dependency on the core script.

```yaml
# Use in your workflows:
jobs:
  check:
    uses: ./.github/workflows/is-version-bump.yml
  your-job:
    needs: check
    if: needs.check.outputs.is_version_bump == 'false'
```

### install-git-semver.yml

Self-update workflow:
- **Manual trigger**: `workflow_dispatch` with optional version
- **Scheduled trigger**: configurable cron (default: Mondays 9am UTC)
- **`workflow_call`**: for chaining from other workflows
- Creates PR with version diff; automerge controlled by config

### Authentication

| Workflow | Auth | Notes |
|----------|------|-------|
| `version-bump.yml` | `GITHUB_TOKEN` | No PAT required |
| `is-version-bump.yml` | `GITHUB_TOKEN` | Just reads commit message |
| `install-git-semver.yml` | `GITHUB_TOKEN` (or PAT) | PAT only needed if branch protection requires checks on PRs |

## File Classification

| File | Type | Can Edit? |
|------|------|-----------|
| `.semver/git-semver` | Implementation | No — update via install workflow |
| `.github/workflows/version-bump.yml` | Workflow | No — update via install workflow |
| `.github/workflows/is-version-bump.yml` | Workflow | No — update via install workflow |
| `.github/workflows/install-git-semver.yml` | Workflow | No — update via install workflow |
| `.semver/config.json` | Config | Yes — your settings |
| `.semver/.version` | Meta | Auto-managed |

## Commit Message Conventions

Workflows rely on commit message prefixes for loop prevention:

| Prefix | Purpose |
|--------|---------|
| `chore: bump version` | Version bump commit — skipped by version-bump.yml, detected by is-version-bump.yml |
| `chore: install` | Install PR commits — skipped by version-bump.yml |

## How it Differs

| | git-semver | semantic-release | release-please |
|-|-----------|-----------------|----------------|
| Dependencies | Python 3 + git | Node.js ecosystem | GitHub-only service |
| Config model | File patterns trigger bump | Commit conventions trigger bump | Commit conventions trigger bump |
| Commit format | Any (doesn't parse commits) | Conventional Commits required | Conventional Commits required |
| Changelog | Optional, from commit messages | Plugin-based | Automatic |
| Auto bump level | Patch only (minor/major manual) | Derived from commit type | Derived from commit type |
| CI platform | GitHub Actions (v1), extensible | Multiple | GitHub only |

The key difference: **file-driven, not commit-driven.** You don't adopt a commit convention — you declare which file changes constitute a release. Patch automation is safe; minor/major releases are semantic decisions that should be deliberate.

## License

MIT
