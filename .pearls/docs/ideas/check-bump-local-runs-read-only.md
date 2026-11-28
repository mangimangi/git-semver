# Keep local check-bump runs read-only

> Captured: 2026-11-28

## Context

While implementing epic gsv-1fc3 (gsv-1fc3.1 to .3), check-bump gained a fixing mode. It is on by default with `"bump_on": "pull_request"` (`push_bump`, `resolve_fix_mode` in `git-semver`). This repo uses that mode, and its `version-check` job runs `git-semver check-bump`. So a local `.vendored/pkg/git-cicd/git-cicd check` on a branch without the bump now makes a `chore: bump version (...)` commit in the developer's checkout. It pushes that commit only when `CICD_WRITE_TOKEN` is exported. README and AGENTS.md now document this and point to `--no-fix`.

## Idea

check-bump fixing mode makes a local commit when run from git-cicd check on an unbumped branch; consider defaulting to --no-fix unless CI is set or CICD_WRITE_TOKEN is present, so local runs stay read-only
