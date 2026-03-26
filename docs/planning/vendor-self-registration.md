# install.sh `_vendor` self-registration

## Problem

When `install.sh` creates a config file (e.g., `.vendored/configs/git-semver.json`), it writes tool-specific settings but not `_vendor` metadata (`repo`, `install_branch`, `protected`). The git-vendored framework expects vendors to self-register these fields.

This only surfaces when adding git-semver to a **new** repo — existing repos already have the `_vendor` block from prior installs. Discovered during madreperla extraction (bootstrapping a fresh repo).

## What needs to change

In `install.sh`, when creating the config file (the `if [ ! -f .vendored/configs/git-semver.json ]` block), the template should include `_vendor` metadata:

```json
{
  "_vendor": {
    "repo": "mangimangi/git-semver",
    "install_branch": "chore/install-git-semver",
    "protected": [".semver/**"],
    "allowed": [".vendored/configs/git-semver.json"]
  },
  "version_file": "VERSION"
}
```

The `_vendor` block should use `$SEMVER_REPO` for the `repo` field so it works with forks.

## Scope

Small change — just the config template in `install.sh`. No behavior change for existing consumers (the `if [ ! -f ... ]` guard means it only affects first-time installs).
