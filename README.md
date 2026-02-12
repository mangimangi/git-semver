# git-semver

Config-driven semantic versioning for git repos. Declare which files matter, get automatic patch bumps on merge. Zero dependencies beyond Python 3 and git.

## Features

- **File-driven, not commit-driven** — declare which file changes constitute a release, no commit conventions required
- **Single script** — one Python file, zero dependencies
- **Config-driven** — `.semver/config.json` controls everything
- **Monorepo support** — subdirectory configs for independent versioning of multiple artifacts
- **Automatic patch bumps** — on merge to main when configured files change
- **Manual minor/major** — deliberate releases via `workflow_dispatch`
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
│   ├── bump-and-release   # CI orchestration script (don't edit)
│   └── config.json        # Your config (edit this!)
└── .github/
    └── workflows/
        └── version-bump.yml          # Auto-bump + release on merge
```

When installed via the git-vendored v2 framework, code files (`git-semver`, `bump-and-release`) may live in `.vendored/pkg/git-semver/` instead of `.semver/`. Config always stays in `.semver/config.json`.

The workflow is a thin shell — all logic lives in the scripts. Updates to versioning behavior are delivered via `install-vendored.yml` without modifying the workflow file.

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
| `--no-push` | update files, commit, tag |
| `--no-commit` | update files only |
| `--subdir <name>` | Bump a specific subdirectory instead of root |
| `--description "..."` | Override auto-collected changelog with a curated description |

### `git-semver bump-all --since <commit>`

Checks all configured components (root + subdirectories) for changed files and bumps all triggered ones in a single commit with individual tags. Used by the workflow for automatic on-push bumps.

| Flag | Behavior |
|------|----------|
| `--since <commit>` | Required — commit ref to diff against |
| `--no-push` | Skip push |
| `--no-commit` | Update files only |

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
| `automerge` | `true` | Version bump commits push directly to main. When `false`, creates a PR instead |

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

Combines version bump and GitHub Release creation in a single workflow. This avoids the GitHub Actions limitation where tag pushes made with `GITHUB_TOKEN` don't trigger other workflows.

The workflow is a **thin shell** that passes GitHub context to `.semver/bump-and-release`. All orchestration logic (config reading, bump mode selection, PR creation, release creation) lives in the script, which is updated via the vendor install pipeline — no workflow modifications needed after initial install.

- **Push trigger**: on merge to main/master. Skips automated commits (`chore: bump version`, `chore: install`). Runs `git-semver bump-all` to check all components (root + subdirectories) and bump triggered ones. Respects `install.on_merge` config.
- **Manual trigger**: `workflow_dispatch` with `bump_type`, optional `subdirectory`, and optional `changelog_description`. Bumps the specified component (root if subdirectory is empty).
- **Auto bumps are patches only.** Minor and major require manual dispatch.
- **Direct push mode** (default): pushes directly to main, then creates GitHub Releases for each tag.
- **PR mode**: when `automerge: false`, creates a branch and PR instead.

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
| `.semver/bump-and-release` | Implementation | No — update via install-vendored |
| `.semver/config.json` | Config | Yes — your versioning settings |
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
