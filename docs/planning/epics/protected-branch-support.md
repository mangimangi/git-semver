# Protected Branch Support

When the default `automerge: true` is used on a repo with protected `main` (requiring PRs), `git push` fails with `GH006: Protected branch update failed`. The bump commit and tags are created locally but never pushed, and the workflow crashes.

## Current architecture

`bump-and-release` orchestrates a monolithic flow:

```
git-semver bump-all --since <sha>
  ├── compute versions
  ├── update files
  ├── git commit
  ├── git tag (version tags + latest)
  ├── git push          ← fails on protected branches
  └── git push --tags --force
create_releases()
  └── gh release create (for each tag at HEAD)
```

Bump and release are coupled — tagging and releasing are baked into the bump command. There's no way to create tags/releases from an already-bumped commit.

## Problem

The `automerge: true` path assumes direct push access to main. Protected branches break this assumption. The `automerge: false` workaround exists but:
- It's not the default, so first-time users hit the error
- The error message doesn't suggest the fix
- Even with `automerge: false`, PR mode works but tags/releases are still created before the PR merges (pointing at a branch commit, not main)

## Design

Split the monolithic flow into two phases: **bump** (create the version commit) and **release** (create tags + GitHub releases). For unprotected branches both happen in one run. For protected branches, release happens after the bump PR merges.

### Phase 1: Bump

`bump-and-release` always uses `--no-push` and handles push strategy itself:

```
git-semver bump-all --since <sha> --no-push
  ├── compute versions
  ├── update files
  └── git commit (no tags, no push)

# Then in bump-and-release:
try: git push (to main)
  success → go to release phase
  fail (protected branch) → create PR, done
```

This requires `git-semver` to support `--no-tag` (or a combined `--no-push` that also skips tagging). Currently `--no-push` skips push but still creates tags locally.

### Phase 2: Release

A new `git-semver tag` (or `release`) command that:
1. Reads VERSION file(s) and config
2. Creates version tag(s) + `latest` tag
3. Pushes tags

```
git-semver tag [--push]
  ├── read current version from VERSION (per component)
  ├── git tag -a v<version> -m v<version>
  ├── git tag -f latest
  └── git push --tags --force (if --push)
```

This runs:
- **Unprotected branches**: immediately after successful push in the same workflow run
- **Protected branches**: in a separate workflow trigger when the bump PR merges

### Workflow changes

`version-bump.yml` currently skips commits starting with `chore: bump version` (loop prevention). For protected branch support:

```yaml
jobs:
  bump:
    # Skip if this is a bump commit (loop prevention)
    if: "!startsWith(github.event.head_commit.message, 'chore: bump version')"
    # ... existing bump logic, now with push fallback ...

  release:
    # Run ONLY for bump commits (tag + release after PR merge)
    if: "startsWith(github.event.head_commit.message, 'chore: bump version')"
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, fetch-tags: true }
      - run: python3 <semver-path> tag --push
      - run: python3 <bump-and-release-path> release-only
```

The `bump` and `release` jobs are mutually exclusive (one or the other runs per push event), so there's no loop.

### Protected branch detection

In `bump-and-release`, detect the push failure:

```python
result = run("git", "push", check=False, capture=True)
if result.returncode != 0:
    if "protected branch" in result.stderr.lower() or "GH006" in result.stderr:
        # Fall back to PR mode
        ...
    else:
        # Genuine push failure, abort
        ...
```

### Changes summary

| Component | Change |
|-----------|--------|
| `git-semver` | Add `tag` subcommand (read VERSION, create tags, optionally push) |
| `git-semver` | `bump`/`bump-all`: `--no-push` should also skip tagging (or add `--no-tag`) |
| `bump-and-release` | Always use `--no-push`, handle push + fallback to PR |
| `bump-and-release` | Add `release-only` mode (tag + GitHub release, no bump) |
| `version-bump.yml` template | Add `release` job for bump-commit triggers |
| `README.md` | Document that protected branches work out of the box |

### Edge cases

- **Squash merges**: If the repo uses squash merges on bump PRs, the tag will point at the squash commit (different SHA from the PR branch commit). This is fine — `git-semver tag` creates tags at HEAD after merge.
- **Merge queue**: GitHub merge queues should work since the release job triggers on the final merge commit.
- **Multiple queued bumps**: The existing concurrency group + `sync_branch()` logic handles this. The release job is idempotent (tag already exists = no-op or force update).
- **Tag already exists**: `git tag -a` will fail if the tag exists. Need to handle this (skip or force). Since we use `-f` for `latest`, should be fine for that tag. For version tags, they should be unique.

## Checklist

- [ ] `git-semver`: Add `tag` subcommand
- [ ] `git-semver`: Make `--no-push` also skip tagging (breaking change? audit callers)
- [ ] `bump-and-release`: Refactor to always `--no-push`, handle push with fallback
- [ ] `bump-and-release`: Add `release-only` entry point
- [ ] `version-bump.yml`: Add release job for bump-commit merges
- [ ] `README.md`: Update docs
- [ ] Tests: Cover protected-branch fallback path
