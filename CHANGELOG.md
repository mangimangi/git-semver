# Changelog

All notable changes to git-semver are recorded here.

## [0.2.0] - 2026-11-28

### Added
- git-deps.labels.json: a documented, versioned labels file (format 1) git-semver reads and writes

### Changed
- latest is no longer created or moved on any path and tags are never force-pushed; a repository or script that fetched from the latest ref names a version tag (vX.Y.Z) or the default branch instead, and an existing latest tag is left in place and ignored

## [0.1.2] - 2026-11-28

### Changed
- Python 3.11 or later is required (requires-python >=3.11; 3.10 reached end of life), and the test job runs on 3.11; the bats tests of ci/setup.sh no longer depend on the Pythons or tool cache of the machine running them
- check-bump fixing mode: with bump_on pull_request (push_bump, --fix/--no-fix) it commits a missing patch bump and pushes it to the pull request branch with CICD_WRITE_TOKEN, refusing target/release branches, forks and moved-on branches; the test suite strips real tokens

