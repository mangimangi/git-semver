# check-bump token env should append to existing GIT_CONFIG_* entries

> Captured: 2026-11-28

## Context

While evaluating epic gsv-1fc3, I reviewed gsv-1fc3.2 (commit c389c96), which makes `git-semver check-bump` push its fix commit with `CICD_WRITE_TOKEN`. The push code is `token_git_env` in `git-semver`.

## Idea

check-bump token env should append to existing GIT_CONFIG_* entries

`token_git_env` sets `GIT_CONFIG_COUNT=2` and `GIT_CONFIG_KEY/VALUE_0..1`. That overwrites any `GIT_CONFIG_*` entries the caller already exported, for example from a CI wrapper. It could read the existing count and append its two entries after them.

It could also support GitHub Enterprise hosts. Today the extraheader host is hardcoded to `https://github.com/`; it could be taken from the origin URL instead.
