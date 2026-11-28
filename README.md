# git-semver

Config-driven semantic versioning for git repos. Declare which files matter, get automatic patch bumps on merge. Zero dependencies beyond Python 3.11 or later and git.

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
- **CI-agnostic core** — the script works anywhere git and Python are available

## Installation

### Via curl (initial install)

```bash
curl -fsSL https://raw.githubusercontent.com/mangimangi/git-semver/main/install.sh | bash -s <version>
```

`<version>` is a release such as `0.1.0` (see the repository's tags); the installer fetches that version's files from its tag. The script is read from `main`, the default branch; git-semver keeps no `latest` tag (see [No `latest` tag](#no-latest-tag)).

`version-bump.yml` is installed only on a first install: when no earlier git-semver install is recorded in the repository (no `.vendored/manifests/git-semver.version` or `git-semver.files`, and no installed `git-semver` script) and the file is absent. An upgrade never adds it, so a repository that removed it keeps it removed, and an existing `version-bump.yml` is left as it is. A repository that releases through git-cicd does not get it even on a first install: when `.vendored/configs/git-cicd.json` has a job step that runs git-semver's `release`, or `.vendored/configs/git-semver.json` sets `"bump_on": "pull_request"`, the installer skips the workflow and says why in one line. The installed-file manifest lists the workflow only when that install wrote it or an earlier install did and it is still there; it never lists a file that is not on disk.

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
        └── version-bump.yml          # Auto-bump + release on merge (first install only; not with git-cicd)
```

`version-bump.yml` is written by a first install only, never by an upgrade, and not into a repository that releases through git-cicd (see [Installation](#installation)).

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
git-semver check-bump [--base <rev>] [--head <rev>] [--fix|--no-fix]  # Fail when configured files changed but the version was not raised; in fixing mode push the patch bump
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
7. Creates annotated tag `vX.Y.Z` (or `<subdir>/vX.Y.Z`); no `latest` tag is created or moved
8. Pushes the commit, then the new tag by name (`git push origin <tag>`, never forced)

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
- Never creates or moves a `latest` tag

| Flag | Behavior |
|------|----------|
| (default) | Create tags locally only |
| `--push` | Create tags and push each created tag by name (`git push origin <tag>`), never forced |
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

### Labels (`git-deps.labels.json`)

A **label** is something the publisher says about a version it already released. The first label is `defect`: the version should not be used (it cannot run, it broke its adopters), usually with the version that fixes it. A version tag is never moved or deleted to say this; the label sits beside it in a file.

The file is `git-deps.labels.json` at the root of the repository, and what counts is the copy on the default branch: whoever keeps that branch vouches for it. A reader such as [git-deps](https://github.com/mangimangi/git-deps) reads it through git; nothing calls a platform. This section is the contract such a reader relies on; [`templates/labels.schema`](templates/labels.schema) is the same format as a JSON Schema.

```json
{
  "format": 1,
  "versions": {
    "v0.1.2": [
      {
        "name": "defect",
        "reason": "medici init fails on a fresh checkout",
        "date": "2026-11-28",
        "commit": "455ee13c1f0e5d8b7a2f3e9c6d4b1a0f8e7d6c5b",
        "fixed_in": "0.1.3"
      }
    ],
    "backend/v2.3.0": [
      {
        "name": "defect",
        "reason": "migrations drop the sessions table",
        "date": "2026-11-28",
        "commit": "0123456789abcdef0123456789abcdef01234567"
      }
    ]
  }
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `format` | integer, required | Format version of the file. This is format `1`; a reader refuses a higher format it does not know |
| `versions` | object, required | Labels per released version, keyed by the full version tag name as `git tag` shows it: `vX.Y.Z` for the root, `<subdir>/vX.Y.Z` for a [subdirectory component](#subdirectory-configs-monorepo-support). Each value is a list of labels |
| `name` | string, required | The label. git-semver makes `defect`; a reader ignores a name it does not know (for example a later `eol`) |
| `reason` | string | Why, in one line (no newline). `git-semver label` requires it for `defect` |
| `date` | string, required | UTC date the label was made, `YYYY-MM-DD` |
| `commit` | string, required | The 40-hex commit the version's tag pointed at when the label was made. A pin is a version and a sha: a reader can tell a label applies to the commit it holds |
| `fixed_in` | string | The version (`X.Y.Z`, same component) that fixes it, when there is one |

**Strict about structure, tolerant about content.** git-semver refuses a file, with a message naming what is wrong and where (for example `versions['v0.1.2'][0]: 'commit' must be a 40-hex commit sha`), when it is not valid JSON, the top level is not an object, `format` is missing, not an integer or not `1`, `versions` is missing or not an object, a key is not a version tag, a value is not a list, or a label is not an object or has a missing or ill-typed `name`, `commit` or `date`, a `reason` that is not a one-line string, or a `fixed_in` that is not an `X.Y.Z` version. It keeps, ignores and writes back unchanged a label name it does not know, an extra field on a label and an extra top-level key. A missing file means no labels.

**Stable under version control.** git-semver writes the file as JSON indented by two spaces, with a trailing newline and non-ASCII characters as they are. Top-level keys are `format`, `versions`, then unknown keys in the order read; versions are sorted by component (root first, then subdirectories by name), then by version precedence (`v0.9.0` before `v0.10.0`); labels in a version are sorted by name, with fields in the order `name`, `reason`, `date`, `commit`, `fixed_in`, then unknown fields in the order read. Reading and writing a file already in this form leaves it byte for byte the same, so a change shows as only the lines it touched.

**`latest` is computed, not a tag.** A reader's latest version is the newest version no label rules out. git-semver does not keep a `latest` tag.

### `git-semver check-bump [--base <rev>] [--head <rev>] [--fix|--no-fix]`

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
| `--fix` / `--no-fix` | Force fixing mode on or off (see below); default the [`push_bump`](#keys) key, which is on with `"bump_on": "pull_request"` |
| `--source-branch <name>` | Pull request branch the fix is pushed to; default `$CICD_SOURCE_BRANCH` |
| `--target-branch <name>` | Branch the pull request goes into; default `$CICD_TARGET_BRANCH` |
| `--config <path>` | Specify a non-default config file |

The check itself is local: it needs no token and no network. With fixing mode off (`"push_bump": false`, `--no-fix`, or `bump_on` other than `pull_request` without `--fix`) it writes nothing (no file edits, commits or tags).

**Fixing mode** (on by default with `"bump_on": "pull_request"`). When the only failures are components whose version is *unchanged* from the base's, the check raises each of them by a **patch** the way `git-semver bump` does (version file, `updates`, changelog entry) and makes one commit on top of the commit under test, `chore: bump version (root 0.1.1 -> 0.1.2, backend 0.3.0 -> 0.3.1)`, holding only the files the bump wrote (other changes in the worktree stay out). The commit under test must be the checked-out `HEAD`; otherwise it is an error naming both. When git has no committer identity (a CI runner), the commit is made as `git-semver <git-semver@users.noreply.github.com>`.

- A component already raised by any amount (patch, minor or major) is left alone: a minor or major bump stays a person's decision. With nothing to fix no commit is made.
- A version that went down, is malformed or is missing is an error, never fixed; when any component is in that state no commit is made at all.

It then pushes the commit, never forced, to the pull request's source branch on `origin` (`git push origin HEAD:refs/heads/<source>`) with the token in `CICD_WRITE_TOKEN`. It does **not** push, and prints `Not pushing the bump: <reason>` plus the `fix:` command to run by hand, when:

| Case | Reason printed |
|------|----------------|
| `CICD_WRITE_TOKEN` is unset or empty (no secret, a fork, the job did not declare it) | `no CICD_WRITE_TOKEN: declare it on the version check job` |
| No source branch (neither `--source-branch` nor `CICD_SOURCE_BRANCH`) | `source branch unknown` |
| The source branch is the target branch | `source branch <b> is the target branch` |
| The source branch is a release branch (the target, `main` or `master`) | `source branch <b> is a release branch` |
| The source branch is not on `origin` (`git ls-remote`; a fork's branch is never in this repository) | `branch <b> is not on origin` |
| The branch on `origin` is no longer the commit under test | `branch <b> moved on from <head> (now <sha>)` |
| `git push` itself fails | `git push failed: <git's message>` |

Whether it pushed or not, the run exits 1: the commit under test lacked the bump, so it never records a pass. When it pushed it says `The pushed commit <sha> starts its own run; wait for that one` — that run checks the bumped commit and passes.

The token is given to git for that one `ls-remote` and push only, through the environment (`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` setting `http.https://github.com/.extraheader`: first an empty value, which drops the header `actions/checkout` stored with `GITHUB_TOKEN`, then `AUTHORIZATION: basic <base64 of x-access-token:token>`). It is never on a command line, never written to `.git/config`, and git's messages are printed with the token and its base64 form replaced by `***`.

`CICD_WRITE_TOKEN` must be able to push to this repository: a fine-grained personal access token or a GitHub App token with **Contents: read and write** on it. `GITHUB_TOKEN` does not do: a push made with it starts no workflow, so the bumped commit would never be checked. To turn pushing off, set `"push_bump": false` (check only, as before) or pass `--no-fix`.

It is meant as the step of a git-cicd `open` job, which sets `CICD_BASE` (the target branch tip), `CICD_HEAD` (the pull request head), `CICD_SOURCE_BRANCH` and `CICD_TARGET_BRANCH`. git-cicd gives a job a secret only when the job declares it, so the job lists `CICD_WRITE_TOKEN` under `secrets` (as git-cicd's README defines it); without the declaration the check fails naming the command, as before:

```json
"version-check": {
  "name": "Version Check",
  "on": ["open"],
  "branches": ["main"],
  "paths": ["**"],
  "steps": [[".vendored/pkg/git-semver/git-semver", "check-bump"]],
  "secrets": ["CICD_WRITE_TOKEN"]
}
```

A local run on a branch that lacks the bump (including `git-cicd check`) makes the fix commit in your checkout too; it is pushed only when `CICD_WRITE_TOKEN` is exported. Pass `--no-fix` to only check.

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

**`push_bump`** (default: `true` with `"bump_on": "pull_request"`; ignored otherwise)

With `bump_on: pull_request`: `git-semver check-bump` raises a missing version by a patch and pushes it to the pull request branch with `CICD_WRITE_TOKEN` (see [`check-bump`](#git-semver-check-bump---base-rev---head-rev---fix--no-fix)). `false` = check only, as before. `--fix`/`--no-fix` override it for one run.

**`bump_on`** (default: `"merge"`)

When the version is bumped. `"merge"` (also when the key is absent) is the bump-on-merge path: `release` bumps after a change lands. `"pull_request"` moves the bump into the pull request: `git-semver check-bump` fails a pull request that changes configured files without raising the version (and, unless `push_bump` is `false`, pushes the missing patch bump to its branch), and `release` with no subcommand only tags the landed commit and publishes it (see [Bumping in the pull request](#bumping-in-the-pull-request-bump_on-pull_request)). Any other value is an error naming the allowed values.

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

### Two ways to release

| | Bump on merge (default) | Bump in the pull request |
|-|-------------------------|--------------------------|
| Setting | `bump_on` absent or `"merge"` | `"bump_on": "pull_request"` |
| Runs | `version-bump.yml` (the default install), or a git-cicd job calling `release` with no subcommand | git-cicd: an `open` job running `git-semver check-bump` on pull requests into the release branch, and a `merge` job calling `release` with no subcommand |
| Who bumps | the release run, after the merge: a `chore: bump version` commit | the pull request's author, with `git-semver bump patch --no-push` (or `minor`/`major`); the check fails until they do |
| What is tagged | the bump commit, which ran no pull request checks | the merged commit, which did |
| `latest` tag | not created or moved | not created or moved |
| Branch protection | the workflow must be able to push to the default branch; when it cannot, the bump falls back to a pull request opened with the workflow's own token, which starts no checks and has to be merged by hand | needs no write access to the branch, only to push tags; turn on "require branches to be up to date before merging" so two pull requests that bump to the same version cannot both land (if one does, the release refuses it loudly instead of tagging) |

### No `latest` tag

No git-semver path creates, moves or pushes a `latest` tag, and tags are never force-pushed: `bump`, `bump-all`, `tag --push` and `release` push each version tag they create by name (`git push origin <tag>`), so a tag held elsewhere is never overwritten. A moved tag made `git fetch --tags` fail in every clone that held the old one ("would clobber existing tag"); a version tag, once pushed, never moves.

A `latest` tag an older git-semver left in a repository is left alone and ignored wherever tags are read as versions (it is never released, never used as a bump baseline and never printed by `git-semver released`). Deleting it is the owner's choice: `git push origin :refs/tags/latest` and `git tag -d latest` in each clone. Anything that read from the `latest` ref pins a version tag (`vX.Y.Z`) or reads the default branch instead; a reader that wants the newest usable version computes it as the newest version no [label](#labels-git-depslabelsjson) rules out.

### Bumping in the pull request (`bump_on: pull_request`)

With `"bump_on": "pull_request"` in `.vendored/configs/git-semver.json`, the bump (version file, changelog, `updates`) is part of the pull request, checked by a [`git-semver check-bump`](#git-semver-check-bump---base-rev---head-rev---fix--no-fix) job (which, with `CICD_WRITE_TOKEN` declared, pushes a missing patch bump to the pull request's branch itself, so the author need not remember it), and `release` with no subcommand, on a merge, does not bump, commit or push to the branch. For the root and each subdirectory it reads the version at the landed commit (`CICD_HEAD`, else `GITHUB_SHA`, else `HEAD`) and:

| The version's tag (`vX.Y.Z` or `<subdir>/vX.Y.Z`) | What `release` does |
|------------------------------------------------|---------------------|
| does not exist | creates it, annotated, at the landed commit |
| exists at the landed commit or an ancestor | nothing for that component |
| exists at another commit, and this merge did not change the version file | nothing to release for that component |
| exists at another commit, and this merge changed the version file to that version | fails (exit 1), naming the tag, the commit that holds it and the fix: bump to a higher version in a new pull request |

Every component is checked before any tag is made, so a failure creates nothing. The new tags are then pushed one by one by name (`git push origin <tag>`, never `--force`, so a tag held elsewhere is never overwritten), with one `gh release create <tag> --generate-notes` each. When every version is already tagged it says so and exits 0, so a second run at the same commit does nothing. Whether the merge changed the version file is read from `CICD_BASE` (else `GITHUB_EVENT_BEFORE`); without one, or with the all-zero SHA, the file counts as changed, so a version already tagged elsewhere fails loudly rather than passing.

- The `latest` tag is not created or moved, here or on any other path (see [No `latest` tag](#no-latest-tag)).
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
| git-cicd version check job (`git-semver check-bump`, `bump_on: pull_request`) | `CICD_WRITE_TOKEN` | Optional; lets the check push the missing patch bump to the pull request branch. Needs Contents: read and write on the repository (fine-grained PAT or App token; a `GITHUB_TOKEN` push starts no workflow). Declare it with `"secrets": ["CICD_WRITE_TOKEN"]` on the job. Without it the check only fails and names the command |

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
| `version-check` | `Open / Version Check / git-semver:version-check` | `git-semver check-bump` at the repository root (pull requests into `main` only): fails when a file in `files` changed and `VERSION` was not raised (the job does not declare `CICD_WRITE_TOKEN` yet, so the bump is not pushed for you here) |

Documents and tracker records (`*.md` at the root, `docs/**`, `commands/*.md`, `LICENSE`, `.pearls` issues, archive and docs, `.madreperla/sessions.jsonl`) need no job. The result is the `Verdict / git-cicd:verdict` commit status on the pull request's head commit.

The `test` job measures line coverage of the two shipped Python scripts, `git-semver` and `release`, including runs a test starts as a subprocess, prints the per-file report with missing lines, and fails when the total or either file is below 99% (`[tool.coverage.*]` in `pyproject.toml`). `install.sh` and the scripts under `ci/` are tested with bats (`tests/bats/*.bats`); each test runs the script in a sandbox whose PATH holds only stubs and a few system tools and whose runner tool cache is an empty directory, so no test depends on the Pythons the machine has.

Run the same checks locally:

```bash
.vendored/pkg/git-cicd/git-cicd check --setup   # installs what the jobs need, then runs them
.vendored/pkg/git-cicd/git-cicd check           # later runs reuse that setup
```

`.github/workflows/git-cicd-open.yml`, `git-cicd-merge.yml`, `git-cicd-cron.yml` and `git-cicd-manual.yml` are generated: after changing the config or upgrading git-cicd, run `.vendored/pkg/git-cicd/git-cicd generate` and commit what it writes.

### How a release happens here

git-semver releases itself through git-cicd, bumping in the pull request (`"bump_on": "pull_request"` in `.vendored/configs/git-semver.json`):

| Job | Row | Runs |
|-----|-----|------|
| `version-check` | `Open / Version Check / git-semver:version-check` | `git-semver check-bump` at the repository root, on pull requests into `main` |
| `release` | `Merge / Release / git-semver:release`, `Manual / Release / git-semver:release` | `release` at the repository root, with no subcommand |

Both run this repository's own scripts (the root `git-semver` and `release`, not the vendored copies under `.vendored/pkg/git-semver/`, which only get a new entry point once a release is installed back), so a change is checked and released by the code on its branch.

- **In the pull request into `main`**: a change to a file listed in `files` bumps `VERSION` in the same pull request, with `./git-semver bump patch --no-push` (or `minor`/`major`). `version-check` fails until it does and prints that command. Pull requests into an integration branch (`plan/**`) are not checked; the pull request into `main` bumps once.
- **On every merge to `main`** the job tags the merged commit with the version it carries (`vX.Y.Z`), pushes the tag and creates its GitHub Release. Nothing is pushed to `main`, and the `latest` tag is not moved. A merge whose version is already released does nothing; a merge that set a version already tagged at another commit fails and names it.
- **By hand**: Actions tab → **Manual** → *Run workflow* on `main`, with `job` = `release`, releases the current commit the same way. The job declares no inputs; a minor or major bump is made in a pull request.

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
| Dependencies | Python + git | Node.js ecosystem | GitHub-only service |
| Config model | File patterns trigger bump | Commit conventions trigger bump | Commit conventions trigger bump |
| Commit format | Any (doesn't parse commits) | Conventional Commits required | Conventional Commits required |
| Changelog | Optional, from commit messages | Plugin-based | Automatic |
| Auto bump level | Patch only (minor/major manual) | Derived from commit type | Derived from commit type |
| CI platform | GitHub Actions (v1), extensible | Multiple | GitHub only |

The key difference: **file-driven, not commit-driven.** You don't adopt a commit convention — you declare which file changes constitute a release. Patch automation is safe; minor/major releases are semantic decisions that should be deliberate.

## License

MIT
