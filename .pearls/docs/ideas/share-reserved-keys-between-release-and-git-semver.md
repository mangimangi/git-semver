# Share reserved keys and component discovery between release and git-semver

> Captured: 2026-11-28

## Context

Came up while evaluating gsv-bbc9.2 (commit d82ae38, the `bump_on: pull_request` tag-on-merge mode in `release`). `release` now has its own `SEMVER_RESERVED_KEYS`, `semver_components`, `format_tag` and `is_version`, which copy `RESERVED_KEYS`, `get_subdirectories`/`get_version_file` and `parse_version` in `git-semver`. The tests pass and coverage is 100%, but nothing keeps the two copies the same.

## Idea

`release` duplicates git-semver's `RESERVED_KEYS`, its component discovery, `format_tag` and its version parsing (`SEMVER_RESERVED_KEYS` in `release`, `RESERVED_KEYS` in `git-semver`). If a reserved key is added to one but not the other, `release` would treat that key as a subdirectory component. Share them instead: have `release` call `git-semver` for the component list, or add a test that asserts the two sets are equal.
