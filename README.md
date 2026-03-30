# git-semver

Config-driven semantic versioning for git repos. Declare which files matter, get automatic patch bumps on merge. Zero dependencies beyond Python 3 and git.

## Features

- **File-driven, not commit-driven** — declare which file changes constitute a release, no commit conventions required
- **Single script** — one Python file, zero dependencies
- **Config-driven** — `.semver/config.json` controls everything
- **Monorepo support** — subdirectory configs for independent versioning of multiple artifacts
- **Automatic patch bumps** — on merge to main when configured files change
- **Manual minor/major** — deliberate releases via `workflow_dispatch`
- **Protected branch support** — auto-detects branch protection and falls back to PR mode
- **Changelog generation** — from commit messages, with configurable noise filters
- **No PAT required** — core versioning uses `GITHUB_TOKEN`
- **CI-agnostic core** — the script works anywhere git and Python 3 are available

## Installation

### Via curl (initial install)

```bash
curl -fsSL https://raw.githubusercontent.com/mangimangi/git-semver/latest/install.sh | bash -s <version>
```

### Via GitHub Actions (ongoing updates)

The `install-vendored.yml` workflow handles updates for all vendored tools (including git-semver):
- Can be triggered manually from the Actions tab with an optional vendor + version
- Creates a PR when updates are available
- Requires [git-vendored](git-vendored/) to be installed first

### What gets installed

```
your-project/
├── .semver/
│   ├── git-semver         # Core versioning script (don't edit)
│   ├── semver             # CI orchestration script (don't edit)
│   └── config.json        # Your config (edit this!)
└── .github/
    └── workflows/
        └── version-bump.yml          # Auto-bump + release on merge
```

When installed via the git-vendored v2 framework, code files (`git-semver`, `semver`) may live in `.vendored/pkg/git-semver/` instead of `.semver/`. Config always stays in `.semver/config.json`.

The workflow is a thin shell — all logic lives in the scripts. Updates to versioning behavior are delivered via `install-vendored.yml` without modifying the workflow file.

> **Protected branches work automatically.** If the main branch is protected, the bump job detects the push failure and falls back to creating a PR. No configuration needed — see [Protected Branch Support](#protected-branch-support) for details.

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
git-semver version [--subdir <name>]                 # Print current version
git-semver check [--since <commit>] [--subdir <name>] # Check if a bump is needed (exit 0=yes, 1=no)
git-semver bump [patch|minor|major] [opts]            # Bump version, commit, tag, push
git-semver bump-all --since <commit> [opts]           # Check all components, bump all triggered
git-semver tag [--push] [--subdir <name>]             # Create version tags from VERSION files
```

All commands accept `--config <path>` to specify a non-default config file.

### `git-semver version`

Reads `version_file` from `.semver/config.json` and prints the current version. Use `--subdir <name>` to read a subdirectory's version instead.

### `git-semver check [--since <commit>]`

Diffs changed files since the given commit (or `HEAD~1` if omitted) against the `files` patterns in config. Exit 0 = bump needed, exit 1 = no bump needed. Outputs matched files and patterns to stdout. Use `--subdir <name>` to check a specific subdirectory.

### `git-semver bump [patch|minor|major]`

The complete version release operation:

1. Reads current version from `version_file`
2. Computes new version (default: `patch`)
3. Writes new version to `version_file`
4. Applies `updates` — pattern-based find-and-replace across configured files
5. Updates changelog (if enabled) — collects commits since last tag, filters noise prefixes, prepends dated entry
6. Commits as `chore: bump version to vX.Y.Z` (or `chore: bump version to <subdir>/vX.Y.Z`)
7. Creates annotated tag `vX.Y.Z` (or `<subdir>/vX.Y.Z`) + updates `latest` tag
8. Pushes commit and tags

| Flag | Behavior |
|------|----------|
| (default) | update files, commit, tag, push |
| `--no-push` | update files, commit (no tag, no push) |
| `--no-commit` | update files only |
| `--subdir <name>` | Bump a specific subdirectory instead of root |
| `--description "..."` | Override auto-collected changelog with a curated description |

### `git-semver bump-all --since <commit>`

Checks all configured components (root + subdirectories) for changed files and bumps all triggered ones in a single commit with individual tags. Used by the workflow for automatic on-push bumps.

| Flag | Behavior |
|------|----------|
| `--since <commit>` | Required — commit ref to diff against |
| `--no-push` | Commit only (no tag, no push) |
| `--no-commit` | Update files only |

### `git-semver tag [--push]`

Creates version tags from VERSION files without modifying any files. Reads the current version from each component's `version_file` and creates annotated tags.

- Root: `vX.Y.Z`
- Subdirectories: `<subdir>/vX.Y.Z`
- Always creates/updates the `latest` tag

| Flag | Behavior |
|------|----------|
| (default) | Create tags locally only |
| `--push` | Create tags and push (`git push --tags --force`) |
| `--subdir <name>` | Tag a specific subdirectory instead of all components |
| `--config <path>` | Specify a non-default config file |

Idempotent: if a version tag already exists at HEAD, no error is raised.

### Local usage

```bash
# Bump patch locally (useful for testing or non-CI workflows)
./git-semver bump patch

# Check if files changed since a specific commit
./git-semver check --since abc123

# Bump without pushing (review before push)
./git-semver bump minor --no-push

# Bump a specific subdirectory
./git-semver bump patch --subdir frontend

# Check all components and bump triggered ones
./git-semver bump-all --since HEAD~5 --no-push

# Create and push version tags (after bump --no-push)
./git-semver tag --push
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
    "automerge": true,
  }
}
```

### Keys

**`version_file`** (default: `"VERSION"`)

Path to the file holding the current version string. Read before a bump, written with the new version after. Does not need to appear in `files` or `updates` — it is managed implicitly.

**`files`** (required for root, or per subdirectory)

Glob patterns for files whose changes trigger an automatic **patch** bump on merge to main. Supports `*`, `**`, and `?` patterns. Only patches are automatic — minor and major bumps are always manual via `workflow_dispatch`.

**`updates`** (required for root, or per subdirectory)

Map of files to update with the new version string when a bump occurs. Two action types:

| Action | Format | Example |
|--------|--------|---------|
| `"file"` | Write entire file as version + newline | `"VERSION": "file"` |
| `["pattern", ...]` | Regex find-and-replace | `"src/lib.py": ["VERSION = "]` |

Pattern matching for updates:
- Pattern containing `=`: matches `pattern + quoted_version`, replaces with `pattern + "new_version"` (preserves quote style)
- Pattern without `=`: matches `pattern + version`, replaces with `pattern + new_version`

**`changelog`** (default: enabled)

Object with optional keys:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable changelog generation |
| `file` | string | `"CHANGELOG.md"` | Path to the changelog file |
| `ignore_prefixes` | array | `[]` | Commit message prefixes to filter out |

Example: `{"enabled": true, "file": "CHANGES.md", "ignore_prefixes": ["chore:", "docs:"]}`

> **Deprecated shorthand**: boolean `true`/`false` values are still accepted for backward compatibility but the object format is preferred.

When enabled, collects commit messages since the last tag, filters out noise prefixes, and prepends a dated entry under `## [version] - date`.

**`install`** — controls installed workflow behavior:

| Key | Default | Description |
|-----|---------|-------------|
| `on_merge` | `true` | Auto-trigger patch bump when `files` change on merge to main. When `false`, bumps are manual-only |
| `automerge` | `true` | Attempt direct push first. When `false`, always create a PR. Note: protected branches are auto-detected — direct push falls back to PR automatically, so this setting is less relevant when branch protection is enabled |

### Subdirectory configs (monorepo support)

Any top-level key in the config that is **not a reserved key** and whose value is a **dict** is treated as a subdirectory configuration. This enables independent versioning of multiple artifacts in the same repo.

Reserved keys: `version_file`, `files`, `updates`, `changelog`, `install` (plus any key starting with `_`).

Each subdirectory config supports: `version_file`, `files`, `updates`, `changelog`. Tags for subdirectories use the format `<subdir>/vX.Y.Z`.

A repo can have root versioning, subdirectory versioning, or both. If only subdirectories are configured, root-level `files` and `updates` are optional.

**Changelog inheritance**: if a subdirectory doesn't specify its own `changelog` key, it inherits the root's enabled/disabled state and `ignore_prefixes`. The changelog file defaults to `<subdir>/CHANGELOG.md` regardless of root's file path.

#### Example: monorepo with frontend and backend

```json
{
  "version_file": "VERSION",
  "files": ["core/**/*.py"],
  "updates": { "VERSION": "file" },
  "changelog": {
    "ignore_prefixes": ["chore:", "docs:"]
  },
  "frontend": {
    "version_file": "frontend/VERSION",
    "files": ["frontend/src/**/*.js", "frontend/package.json"],
    "updates": {
      "frontend/VERSION": "file",
      "frontend/package.json": ["\"version\": "]
    }
  },
  "backend": {
    "version_file": "backend/VERSION",
    "files": ["backend/**/*.py"],
    "updates": {
      "backend/VERSION": "file",
      "backend/setup.py": ["version="]
    }
  }
}
```

This config produces:
- Root changes to `core/**/*.py` → tag `v1.2.3`
- Frontend changes → tag `frontend/v1.0.1`
- Backend changes → tag `backend/v2.3.0`

Each component is versioned and tagged independently. On merge, `bump-all` checks all components and bumps whichever ones had matching file changes. Manual dispatch via `workflow_dispatch` lets you bump a specific subdirectory with `minor` or `major`.

## GitHub Actions

### version-bump.yml (Bump & Release)

A two-job workflow that handles version bumping and GitHub Release creation. The two jobs are mutually exclusive, preventing loops.

The workflow is a **thin shell** that passes GitHub context to `.semver/release`. All orchestration logic (config reading, bump mode selection, PR creation, release creation) lives in the script, which is updated via the vendor install pipeline — no workflow modifications needed after initial install.

#### Bump job

Runs when a non-bump commit lands on main (push) or on manual trigger (workflow_dispatch). Calls `semver bump`.

- **Push trigger**: Skips `chore: bump version` and `chore: install` commits. Runs `git-semver bump-all --no-push` then attempts `git push`. If push fails due to branch protection, falls back to creating a PR.
- **Manual trigger**: `workflow_dispatch` with `bump_type`, optional `subdirectory`, and optional `changelog_description`.
- **Auto bumps are patches only.** Minor and major require manual dispatch.
- **Protected branches**: auto-detected. If `git push` fails with a protection error (`GH006`), the bump job creates a branch and PR instead. No configuration needed.
- **PR mode**: when `automerge: false`, skips the push attempt and goes straight to PR.

#### Publish job

Runs when a `chore: bump version` commit lands on main (either direct push or merged PR). Calls `semver publish`.

- Creates version tags via `git-semver tag --push`
- Creates GitHub Releases for each version tag (skips `latest`)
- Handles monorepo: creates releases for all component tags

The bump and publish jobs never run together — their `if` conditions are mutually exclusive.

### Protected Branch Support

Protected branches work automatically with no configuration changes. The flow adapts based on whether `git push` succeeds:

**Unprotected branch (default):**
```
push to main → bump job: bump + push → publish job: tag + release
```

**Protected branch (auto-detected):**
```
push to main → bump job: bump + PR → PR merged → publish job: tag + release
```

The bump job always uses `git-semver bump-all --no-push` (which creates the commit but no tags), then attempts `git push`. If push fails due to branch protection (`GH006` error), it creates a branch and PR with the bump commit. When the PR merges, the publish job detects the `chore: bump version` commit and creates tags + releases.

Squash merges work correctly: GitHub uses the PR title as the squash commit message, which preserves the `chore: bump version` prefix that triggers the publish job.

### Authentication

| Workflow | Auth | Notes |
|----------|------|-------|
| `version-bump.yml` | `GITHUB_TOKEN` | No PAT required |
| `install-vendored.yml` | `GITHUB_TOKEN` / `VENDOR_PAT` | `VENDOR_PAT` only needed for private vendor repos |

## Vendor Management

git-semver uses [git-vendored](git-vendored/) for unified install/protection across all vendored tools. See the [git-vendored README](git-vendored/) for full details.

### Installed vendor infrastructure

```
.vendored/
├── config.json        # Vendor registry (edit this to add vendors)
├── .version           # git-vendored version tracker
├── install            # Vendored script — installs/updates vendors
└── check              # Vendored script — protects vendor files on PR
.dogfood/
├── .version           # git-dogfood version tracker
└── resolve            # Vendored script — finds dogfood vendor
.github/workflows/
├── install-vendored.yml   # Installs/updates any vendor
├── check-vendor.yml       # Blocks direct edits to vendor files
└── dogfood.yml            # Triggers self-update after release
```

### How it works

1. **install-vendored.yml** — single workflow handles all vendor updates (schedule, manual, or called by dogfood)
2. **check-vendor.yml** — runs `.vendored/check` on PRs to block unauthorized vendor file edits
3. **dogfood.yml** — after Bump & Release succeeds, finds the vendor with `dogfood: true` and triggers install-vendored

### Vendor lifecycle

```
code change → bump & release → dogfood → install-vendored → PR → merge
              (git-semver)     (git-dogfood) (git-vendored)
```

## File Classification

| File | Type | Can Edit? |
|------|------|-----------|
| `.semver/git-semver` | Implementation | No — update via install-vendored |
| `.semver/release` | Implementation | No — update via install-vendored |
| `.semver/config.json` | Config | Yes — your versioning settings |
| `.vendored/manifests/git-semver.schema` | Schema | No — installed by git-semver, used by `audit` |
| `.vendored/install` | Implementation | No — update via install-vendored |
| `.vendored/check` | Implementation | No — update via install-vendored |
| `.vendored/config.json` | Config | Yes — vendor registry |
| `.vendored/.version` | Meta | Auto-managed |
| `.dogfood/resolve` | Implementation | No — update via install-vendored |
| `.github/workflows/version-bump.yml` | Workflow | No — installed by git-semver |
| `.github/workflows/install-vendored.yml` | Workflow | No — installed by git-vendored |
| `.github/workflows/check-vendor.yml` | Workflow | No — installed by git-vendored |
| `.github/workflows/dogfood.yml` | Workflow | No — installed by git-dogfood |

## Commit Message Conventions

Workflows rely on commit message prefixes for loop prevention:

| Prefix | Purpose |
|--------|---------|
| `chore: bump version` | Version bump commit — skipped by Bump & Release workflow |
| `chore: install` | Install PR commits — skipped by Bump & Release workflow |

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
