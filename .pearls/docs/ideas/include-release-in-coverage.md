# Include release in coverage

> Captured: 2026-11-28

## Context

Evaluating epic gsv-81b6 (one-step `release` entry point, `git-semver released`, git-cicd release job). gsv-81b6.1 added ~150 lines to the root `release` script plus tests in `tests/test_bump_and_release.py`. The acceptance criterion "coverage must not drop" could not be enforced: `pyproject.toml` `[tool.coverage.run] include = ["git-semver"]` measures only `git-semver`. Measured by hand, `release` is at 95% (196 statements, 9 missed: lines 67-76, 389).

## Idea

Include release in coverage: add `release` to `[tool.coverage.run] include` in `pyproject.toml` so the `test` job's coverage report (and any threshold) covers the CI orchestration script too, and a coverage drop in `release` shows up in CI.
