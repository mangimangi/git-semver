# AGENTS.md

Config-driven semantic versioning for git repos. File changes trigger patch bumps on merge; minor/major are manual.

## Key Files

| File | Role |
|------|------|
| `git-semver` | Core Python script — `version`, `check`, `bump`, `bump-all`, `tag` subcommands |
| `release` | CI orchestration — called by `version-bump.yml` for bump + publish |
| `install.sh` | Installs git-semver into consumer repos |
| `.vendored/configs/git-semver.json` | Versioning config for this repo (dogfooded) |
| `.github/workflows/version-bump.yml` | Bump on merge, publish on bump commit |
| `.github/workflows/test.yml` | Runs pytest on PRs |

## Development

Scripts use Python 3 with no external dependencies. Type annotations are used throughout.

### Running Tests

```bash
pip install pytest pytest-cov pyyaml
pytest tests/ -v --cov --cov-report=term-missing
```

Test config is in `pyproject.toml`. Tests cover: patterns, versions, config loading, bump/release, updates, git helpers, changelog, commands, install.

### Conventions

- One commit per logical change
- Vendored files (`.vendored/pkg/`, `.vendored/install`, `.vendored/check`) are managed by git-vendored — do not edit directly
- Config changes go in `.vendored/configs/git-semver.json`
- Workflow files are installed artifacts — do not edit

## Vendor Infrastructure

This repo dogfoods its own tooling. After a release, `dogfood.yml` triggers `install-vendored.yml` to self-update. `check-vendor.yml` blocks unauthorized edits to vendored files on PRs.

## Issue Tracking

Uses `prl` (pearls). Run `prl docs` for full CLI reference.
