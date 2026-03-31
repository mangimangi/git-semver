# Fix: publish job doesn't fire on unprotected branches

> **Status:** Ready for refinement

## Problem

The version-bump workflow splits into two jobs: `bump` and `publish`. This was designed for protected branches where bump can't push directly and falls back to a PR. When the PR merges, a new workflow run triggers and the `publish` job matches `startsWith(github.event.head_commit.message, 'chore: bump version')`, creating tags and releases.

On **unprotected branches**, the bump job pushes directly with `GITHUB_TOKEN`. GitHub Actions policy prevents `GITHUB_TOKEN` pushes from triggering new workflow runs (to avoid infinite loops). So the publish job never fires and **no tags or releases are created**.

### Impact

Any repo with an unprotected main branch gets VERSION file bumps but no git tags or GitHub releases. Consumers that resolve versions from tags/releases (e.g., `.vendored/install`) see stale versions.

Currently affected: pearls (0.2.37 in VERSION, latest tag v0.2.36), madreperla (0.0.6 in VERSION, latest tag v0.0.5).

## Fix

When `try_push_or_pr()` returns `True` (direct push succeeded, meaning unprotected branch), tag and release in the same job — there won't be a second run to do it.

In `release`, both `handle_push_bump()` and `handle_dispatch_bump()`:

```python
pushed = try_push_or_pr(commit_title)
if pushed:
    # Unprotected branch — publish job won't fire, so tag here
    git_semver("tag", "--push")
    create_releases()
```

If `try_push_or_pr()` returns `False` (fell back to PR), do nothing — the publish job handles tagging when the PR merges.

The workflow YAML doesn't need changes — the fix is entirely in the `release` script.

## Acceptance criteria

- [ ] After a direct push bump on an unprotected branch, tags and GitHub releases are created in the same workflow run
- [ ] Protected branch flow (PR fallback → merge → publish job) still works unchanged
- [ ] `workflow_dispatch` bump also tags correctly on unprotected branches
- [ ] Tests cover both paths: direct push → immediate tag, PR fallback → deferred tag
