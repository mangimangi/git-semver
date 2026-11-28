# Changelog

All notable changes to git-semver are recorded here.

## [0.1.2] - 2026-11-28

### Changed
- The Python floor is 3.11 (`requires-python = ">=3.11"`); 3.10 reached end of life in October 2026
- check-bump fixing mode: with bump_on pull_request (push_bump, --fix/--no-fix) it commits a missing patch bump and pushes it to the pull request branch with CICD_WRITE_TOKEN, refusing target/release branches, forks and moved-on branches; the test suite strips real tokens

