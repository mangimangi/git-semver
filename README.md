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
│   ├── release            # CI orchestration script (don't edit)
│   └── config.json        # Your config (edit this!)
└── .github/
    └── workflows/
        └── version-bump.yml          # Auto-bump + release on merge
```

When installed via the git-vendored v2 framework, code files (`git-semver`, `release`) may live in `.vendored/pkg/git-semver/` instead of `.semver/`. Config lives at `.vendored/configs/git-semver.json`.

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
git-semver released [<ref>]                           # Print the version tags released at a commit
git-semver check-bump [--base <rev>] [--head <rev>]  # Fail when configured files changed but the version was not raised
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

Idempotent: if a version tag already exists (at any commit), it is skipped. In a monorepo this is the expected state for untouched components — only the bumped component has a new version that needs tagging.

### `git-semver released [<ref>]`

Prints the version tags pointing at a commit (default `HEAD`), one per line, sorted, as full tag names: `vX.Y.Z` for the root, `<subdir>/vX.Y.Z` for a subdirectory. Never prints `latest` or any other non-version tag. When no version was released at the commit it prints nothing and exits 0; a ref that is not a commit is an error (exit 1).

Read-only and local: it reads only the repository's tags, so it needs no config file, no token and no network. A repository's own step after git-semver's release uses it to tell whether this run released a version, and which (see [Publishing after a release](#publishing-after-a-release)).

```bash
git-semver released              # e.g. v1.4.0
git-semver released "$CICD_HEAD" # ask about a specific commit
```

### `git-semver check-bump [--base <rev>] [--head <rev>]`

Fails a pull request that changes configured files without raising the version. For the root and for each subdirectory component, when a file changed on `<head>` since it left `<base>` (`git diff <base>...<head>`, as git-cicd computes a pull request's changed files) matches the component's `files`, the version in its `version_file` at `<head>` must be a valid `X.Y.Z` strictly higher than the one at `<base>` (the target branch). Any increase passes: patch, minor or major.

- No configured file and no version file changed: passes and says so (`root: no configured file changed`).
- Version unchanged, lower, missing or malformed: fails (exit 1), naming the component, the version at the base and the version found, and prints the command that fixes it: `git-semver bump patch --no-push` (root) or `git-semver bump patch --no-push --subdir <name>` (minor or major are accepted too). `--no-push` commits the bump on the branch without tagging or pushing; the tag is made on merge.
- Version file changed alone: passes when the version went up, fails when it went down or is malformed.
- A version file missing at the base counts as no base version: any valid version at the head passes.
- A component with no `files` configured is skipped with a message.

| Flag | Behavior |
|------|----------|
| `--base <rev>` | Commit to compare with; default `$CICD_BASE`. Required from one or the other |
| `--head <rev>` | Commit under test; default `$CICD_HEAD`, else `HEAD` |
| `--config <path>` | Specify a non-default config file |

Read-only and local: it needs no token and no network, and writes nothing (no file edits, commits or tags). It is meant as the step of a git-cicd `open` job, which sets `CICD_BASE` (the target branch tip) and `CICD_HEAD` (the pull request head):

```json
"version-check": {
  "name": "Version Check",
  "on": ["open"],
  "branches": ["main"],
  "paths": ["**"],
  "steps": [[".vendored/pkg/git-semver/git-semver", "check-bump"]]
}
```

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

**`bump_on`** (default: `"merge"`)

When the version is bumped. `"merge"` (also when the key is absent) is the bump-on-merge path: `release` bumps after a change lands. `"pull_request"` moves the bump into the pull request: `git-semver check-bump` fails a pull request that changes configured files without raising the version, and `release` with no subcommand only tags the landed commit and publishes it (see [Bumping in the pull request](#bumping-in-the-pull-request-bump_on-pull_request)). Any other value is an error naming the allowed values.

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

### `release` with no subcommand

`release` can also be called with no subcommand. It then works out for itself which case the run is in and does it, so the bump-or-publish decision needs no workflow `if` conditions and no per-repo wrapper script:

| Run | Landed commit's subject | What `release` does |
|-----|-------------------------|---------------------|
| merge (a change landed on a branch) | starts with `chore: bump version` | publish: `git-semver tag --push` and a GitHub Release per version tag (as `release publish`) |
| merge | starts with `chore: install` | nothing, exit 0 |
| merge | anything else | bump, as `release bump` on push: honours `on_merge` and `automerge`, falls back to a PR on a protected branch, and tags and releases in the same run when the direct push worked |
| manual (started by hand) | — | bump, as `release bump` on `workflow_dispatch`, with `bump_type` (default `patch`), `subdirectory` and `changelog_description` |
| any other trigger (`open`, `cron`, another GitHub event, or none) | — | refused with a reason, non-zero exit |

It reads the run from git-cicd's variables when they are set and from the GitHub Actions variables otherwise; whenever both are set (a git-cicd job on Actions), git-cicd's win:

| git-cicd | GitHub Actions | Meaning |
|----------|----------------|---------|
| `CICD_TRIGGER` (`merge`, `manual`) | `GITHUB_EVENT_NAME` (`push`, `workflow_dispatch`) | Which case |
| `CICD_BASE` | `GITHUB_EVENT_BEFORE` | Commit before the push (what `bump-all --since` diffs against) |
| `CICD_HEAD` | `GITHUB_SHA` (else `HEAD`) | Landed commit whose subject is tested |
| `CICD_TARGET_BRANCH` | `GITHUB_REF` | Branch fast-forwarded to before bumping or tagging |
| `CICD_INPUT_BUMP_TYPE`, `CICD_INPUT_SUBDIRECTORY`, `CICD_INPUT_CHANGELOG_DESCRIPTION` | `INPUT_BUMP_TYPE`, `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION` | Manual-run inputs |

`gh` reads its token from `GH_TOKEN` or `GITHUB_TOKEN` (git-cicd's merge and manual workflows pass `GITHUB_TOKEN`). `release bump` and `release publish` are unchanged; `version-bump.yml` keeps calling them.

### Bumping in the pull request (`bump_on: pull_request`)

With `"bump_on": "pull_request"` in `.vendored/configs/git-semver.json`, the bump (version file, changelog, `updates`) is part of the pull request, checked by a [`git-semver check-bump`](#git-semver-check-bump---base-rev---head-rev) job, and `release` with no subcommand, on a merge, does not bump, commit or push to the branch. For the root and each subdirectory it reads the version at the landed commit (`CICD_HEAD`, else `GITHUB_SHA`, else `HEAD`) and:

| The version's tag (`vX.Y.Z` or `<subdir>/vX.Y.Z`) | What `release` does |
|------------------------------------------------|---------------------|
| does not exist | creates it, annotated, at the landed commit |
| exists at the landed commit or an ancestor | nothing for that component |
| exists at another commit, and this merge did not change the version file | nothing to release for that component |
| exists at another commit, and this merge changed the version file to that version | fails (exit 1), naming the tag, the commit that holds it and the fix: bump to a higher version in a new pull request |

Every component is checked before any tag is made, so a failure creates nothing. The new tags are then pushed one by one by name (`git push origin <tag>`, never `--force`, so a tag held elsewhere is never overwritten), with one `gh release create <tag> --generate-notes` each. When every version is already tagged it says so and exits 0, so a second run at the same commit does nothing. Whether the merge changed the version file is read from `CICD_BASE` (else `GITHUB_EVENT_BEFORE`); without one, or with the all-zero SHA, the file counts as changed, so a version already tagged elsewhere fails loudly rather than passing.

- The `latest` tag is not created or moved on this path.
- The commit-subject rules (`chore: bump version`, `chore: install`) are not consulted.
- A manual run releases the current commit the same way. The bump inputs do not apply: a non-empty `bump_type`, `subdirectory` or `changelog_description` is refused with the reason and the command to use instead (`git-semver bump <type> --no-push` on a branch). Declare no inputs on such a job.
- Two pull requests can each bump to the same version without a git conflict; the second to merge fails here. Turn on "require branches to be up to date before merging" on the release branch so the second has to re-run `check-bump` against the first.

`release bump`, `release publish` and the default `bump_on: merge` behave as before.

### Releasing with git-cicd (instead of version-bump.yml)

`version-bump.yml` stays the default install. A repository that runs its CI through [git-cicd](https://github.com/mangimangi/git-cicd) can instead release with a git-cicd job that calls `release` with no subcommand; the job replaces `version-bump.yml` (remove that workflow when you add the job, so a merge is not released twice). Declare it in `.vendored/configs/git-cicd.json`:

```json
"release": {
  "name": "Release",
  "on": ["merge"],
  "branches": ["main"],
  "paths": ["**"],
  "steps": [".vendored/pkg/git-semver/release"],
  "inputs": {
    "bump_type": {
      "description": "Version bump type",
      "choices": ["patch", "minor", "major"],
      "default": "patch"
    },
    "subdirectory": {
      "description": "Subdirectory to bump (leave empty for root)",
      "default": ""
    },
    "changelog_description": {
      "description": "Changelog entry text (leave empty to collect from commits)",
      "default": ""
    }
  }
}
```

then run `.vendored/pkg/git-cicd/git-cicd generate` and commit the generated `git-cicd-merge.yml` and `git-cicd-manual.yml`.

- **On merge** to `main`, `release` tests the landed commit: a bump commit is tagged and released, an install commit is left alone, anything else is bumped (see [`release` with no subcommand](#release-with-no-subcommand)). `paths: ["**"]` makes every merge reach `release`; whether a bump is needed is `git-semver bump-all`'s decision. Keep `VERSION` out of `needs_nothing`, or a bump commit would need no job and never be published.
- **By hand**, the Actions tab's **Manual** workflow runs the job with `job` = `release` and `inputs` = a JSON object such as `{"bump_type": "minor", "subdirectory": "backend"}`; the inputs reach `release` as `CICD_INPUT_BUMP_TYPE`, `CICD_INPUT_SUBDIRECTORY` and `CICD_INPUT_CHANGELOG_DESCRIPTION`.
- git-cicd's merge and manual workflows already give the job `contents: write` and `pull-requests: write`, fetch all history and tags, pass `GITHUB_TOKEN` (which `gh` reads) and run one after another, as `version-bump.yml`'s concurrency group does.

### Publishing after a release

git-semver's publish is a tag plus a GitHub Release. Publishing anything else (a package to PyPI, a container image) is the repository's own later step in the same git-cicd job, after `release`:

```json
"release": {
  "name": "Release",
  "on": ["merge"],
  "branches": ["main"],
  "paths": ["**"],
  "steps": [".vendored/pkg/git-semver/release", "ci/publish-image.sh"]
}
```

The later step asks `git-semver released` whether this run released a version and stops when none was:

```bash
#!/bin/bash
# ci/publish-image.sh
set -euo pipefail
tags=$(.vendored/pkg/git-semver/git-semver released)
[ -z "$tags" ] && exit 0
for tag in $tags; do
    echo "publishing $tag"
    # build and push the image for $tag
done
```

With an unprotected branch, the run for the merged change bumps, pushes, tags and releases in one go, so its later step sees the new version. With a protected branch, the run for the merged change only opens the bump pull request and its later step sees nothing; the version is seen by the later step of the run for the merged bump commit (`chore: bump version ...`), which is the run that tags and releases.

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

git-semver uses git-vendored for unified install/protection across all vendored tools.

### Installed vendor infrastructure

```
.vendored/
├── config.json              # Vendor registry (edit this to add vendors)
├── install                  # Vendored script — installs/updates vendors
├── check                    # Vendored script — protects vendor files on PR
├── configs/
│   └── git-semver.json      # Your versioning config (edit this!)
├── manifests/               # Version and schema tracking per vendor
└── pkg/
    ├── git-semver/          # Core scripts (git-semver, release)
    └── git-cicd/            # Runs this repo's pull request checks and release
.github/workflows/
├── git-cicd-open.yml        # Generated by git-cicd: pull request checks
├── git-cicd-merge.yml       # Generated by git-cicd: release on merge to main
├── git-cicd-cron.yml        # Generated by git-cicd: the weekly update-vendored run
└── git-cicd-manual.yml      # Generated by git-cicd: release or update-vendored by hand
```

### How it works

1. **The `update-vendored` job** (see [How vendored tools are updated here](#how-vendored-tools-are-updated-here)) installs or updates the vendored tools and opens the install pull requests. In this repository it replaces `install-vendored.yml`, which git-vendored still installs elsewhere.
2. **The `vendor-check` job** (below) runs `.vendored/check` on PRs to block unauthorized vendor file edits. In this repository it replaces `check-vendor.yml`, which git-vendored still installs elsewhere.

### Pull request checks

git-semver's own pull request checks (and its release, below) run through [git-cicd](https://github.com/mangimangi/git-cicd). They are declared as jobs in `.vendored/configs/git-cicd.json`:

| Job | Row | Runs |
|-----|-----|------|
| `test` | `Open / Unit Tests / git-semver:test` | `ci/setup.sh` (installs the Python floor from `requires-python` in `pyproject.toml`, plus pytest, coverage and pyyaml, into a venv, and bats-core), then `ci/test.sh` (pytest under coverage, the coverage gate, then the bats tests in `tests/bats/`) |
| `vendor-check` | `Open / Vendor Check / git-semver:vendor-check` | `.vendored/check` |

Documents and tracker records (`*.md` at the root, `docs/**`, `commands/*.md`, `LICENSE`, `.pearls` issues, archive and docs, `.madreperla/sessions.jsonl`) need no job. The result is the `Verdict / git-cicd:verdict` commit status on the pull request's head commit.

The `test` job measures line coverage of the two shipped Python scripts, `git-semver` and `release`, including runs a test starts as a subprocess, prints the per-file report with missing lines, and fails when the total or either file is below 99% (`[tool.coverage.*]` in `pyproject.toml`). `install.sh` and the scripts under `ci/` are tested with bats (`tests/bats/*.bats`); each test runs the script in a sandbox whose PATH holds only stubs and a few system tools.

Run the same checks locally:

```bash
.vendored/pkg/git-cicd/git-cicd check --setup   # installs what the jobs need, then runs them
.vendored/pkg/git-cicd/git-cicd check           # later runs reuse that setup
```

`.github/workflows/git-cicd-open.yml`, `git-cicd-merge.yml`, `git-cicd-cron.yml` and `git-cicd-manual.yml` are generated: after changing the config or upgrading git-cicd, run `.vendored/pkg/git-cicd/git-cicd generate` and commit what it writes.

### How a release happens here

git-semver releases itself through git-cicd too, with a `release` job in `.vendored/configs/git-cicd.json`:

| Job | Row | Runs |
|-----|-----|------|
| `release` | `Merge / Release / git-semver:release`, `Manual / Release / git-semver:release` | `release` at the repository root, with no subcommand |

- **On every merge to `main`** the job runs this repository's own `release` (the root script, not the vendored copy under `.vendored/pkg/git-semver/`, which only gets a new entry point once a release is installed back). A merge that changed a file listed in `files` in `.vendored/configs/git-semver.json` is bumped (a patch) and the bump commit pushed; a merged `chore: bump version` commit is tagged and gets a GitHub Release; a `chore: install` commit does nothing.
- **By hand**: Actions tab → **Manual** → *Run workflow* on `main`, with `job` = `release` and `inputs` = a JSON object of `bump_type` (`patch`, `minor` or `major`; default `patch`), `subdirectory` and `changelog_description`, for example `{"bump_type": "minor", "changelog_description": "One-step release"}`.

### How vendored tools are updated here

The vendored tools (git-cicd, git-semver, git-vendored) are updated by the `update-vendored` job in `.vendored/configs/git-cicd.json`:

| Job | Row | Runs |
|-----|-----|------|
| `update-vendored` | `Cron / Install Vendored / git-semver:update-vendored`, `Manual / Install Vendored / git-semver:update-vendored` | `ci/update-vendored.sh`: `.vendored/install <vendor> --version <version> --pr --deps=install` (plus `--private` when `private` is `true`) |

- **Every Monday at 09:00 UTC** (`cron` `0 9 * * 1`) it runs on `main` for all vendors at their latest version and opens a pull request for each update.
- **By hand**: Actions tab → **Manual** → *Run workflow* on `main`, with `job` = `update-vendored` and `inputs` = a JSON object of `vendor` (default `all`), `version` (default `latest`) and `private` (`true` or `false`; default `false`, `true` uses `VENDOR_PAT`), for example `{"vendor": "git-cicd", "version": "latest"}`.

The inputs reach the script as `CICD_INPUT_*` variables and are passed to `.vendored/install` as separate arguments, never through a shell. `GH_TOKEN` is the `VENDOR_PAT` secret when it is set, else the workflow's `GITHUB_TOKEN`.

### Vendor lifecycle

```
code change → release job → tag and GitHub Release
              (git-semver, run by git-cicd)

vendor update → update-vendored job → PR → merge
                (.vendored/install, run by git-cicd)
```

## File Classification

| File | Type | Can Edit? |
|------|------|-----------|
| `.vendored/pkg/git-semver/git-semver` | Implementation | No — update via install-vendored |
| `.vendored/pkg/git-semver/release` | Implementation | No — update via install-vendored |
| `.vendored/configs/git-semver.json` | Config | Yes — your versioning settings |
| `.vendored/manifests/git-semver.schema` | Schema | No — installed by git-semver, used by `audit` |
| `.vendored/install` | Implementation | No — update via install-vendored |
| `.vendored/check` | Implementation | No — update via install-vendored |
| `.vendored/config.json` | Config | Yes — vendor registry |
| `.vendored/manifests/*` | Meta | Auto-managed |
| `.github/workflows/version-bump.yml` | Workflow | No — installed by git-semver |
| `.github/workflows/check-vendor.yml` | Workflow | No — installed by git-vendored |

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
