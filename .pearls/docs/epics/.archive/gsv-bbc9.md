# git-semver: the version is bumped in the pull request and tagged on merge

> Unit 11 of plan `git-dev-883c` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-883c.md`; the design is in `mangimangi/git-dev`, `.pearls/docs/what-reaches-main-policy.md`). Added to the plan by the owner on 2026-11-28. Delivers into `plan/git-dev-883c`. Re-check every code reference against the code before using it.

## Problem

The owner, 2026-11-28: "the version bumps should feel seamless".

Today a release is made after the merge, by pushing to the branch that was just merged into. `release` with no subcommand (`cmd_auto`, `release` line 351) sees a merge that touched the configured `files`, runs `git-semver bump-all --since <before> --no-push`, commits `chore: bump version vX.Y.Z` and pushes it to `main`; when the branch is protected it falls back to opening a pull request, and the tag and GitHub release happen only when that bump commit lands and a second run publishes.

What that cost on 2026-11-28, on git-semver's own first release through git-cicd (after #100): `Push rejected by branch protection, falling back to PR`; the bump pull request (#101) was opened with the workflow's own token, so GitHub started no workflows for it; it had zero checks, was `blocked`, and the owner merged it by hand. With `main` protected that is every release. Three further costs of the same design:

- the commit that gets tagged is the bump commit, which ran no checks;
- the bump commit re-triggers the workflow, which is why commits are told apart by their message (`chore: bump version`, `chore: install`);
- a release needs write access to the default branch.

## The design (agreed; do not reopen)

The owner, 2026-11-28: "I like option 1 [no bump commit on `main`; the release tags the merge commit] but I think we modify semver so instead of bumping version on merge it still tags there but has an on open that checks version is bumped appropriately".

- **In the pull request:** a git-semver check fails when the change touches the configured `files` and the version is not higher than the target branch's. The bump (version file, changelog, `updates`) is part of the pull request.
- **On merge:** the release tags the landed commit with the version it carries and publishes it. Nothing is pushed to the branch.
- The check fails and names the one command to run; it does not push (owner: check-only first; fixing it for the author is a later opt-in).
- Any increase satisfies the check: a pull request may bump patch, minor or major.
- The check applies to pull requests into the branches the repository releases from, so work merging into an integration branch (`plan/**`) is not asked to bump; the pull request into `main` bumps once.
- Two pull requests can each bump to the same version and merge without a git conflict. The release must refuse, loudly, to tag a version that is already tagged at another commit. (The owner turns on "require branches to be up to date before merging" for `main`.)
- The moving `latest` tag is dropped (decided earlier): on this path the release does not create or move it.
- `release bump` and `release publish`, and the bump-on-merge behaviour of `release` with no subcommand, stay for every repository still on them. `install.sh` and `templates/github/workflows/version-bump.yml` do not change.
- Coverage: the `test` job fails below 99% for `git-semver` or `release`; every change here comes with its tests, and shell changes with bats tests.
- No vendor-protected file is added, changed or deleted. Run `python3 .vendored/check --base origin/plan/git-dev-883c` before finishing.

## What ships

- A check that the version was bumped, for a pull request — **gsv-bbc9.1** (`git-semver check-bump`)
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `git-semver` (a new subcommand beside `cmd_check` line 448 and `cmd_bump` line 484), `tests/`, `README.md`, `docs/`
  - shape: A read-only command compares the change under test with its base: for the root and for each configured subdirectory, when a changed file matches that component's `files`, the version in its version file must be a valid version higher than the base's; otherwise the command fails, names the component, the base version and the version found, and prints the exact command that fixes it (`git-semver bump ...`). When no configured file changed it passes and says so. A version file that changed without any configured file changing passes when the version went up and fails when it went down or is malformed. It takes the base and head from git-cicd's variables (`CICD_BASE`, `CICD_HEAD`) when set and from arguments otherwise, needs only the local repository (no token, no network), and never writes. It is suitable as a step of an `open` job: `"steps": [[".vendored/pkg/git-semver/git-semver", "<subcommand>"]]`.

- A release that tags the landed commit and pushes nothing to the branch — **gsv-bbc9.2** (`"bump_on": "pull_request"`)
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `release` (`cmd_auto` line 351, `create_releases`), `git-semver` (`cmd_tag` line 593, the `latest` tagging at lines 509 and 584), `.vendored/configs/git-semver.json` schema (`templates/config.schema`), `tests/`, `README.md`
  - shape: A repository chooses this mode in its git-semver config (one documented setting; the default stays today's behaviour). In this mode `release` with no subcommand, on a merge, does not bump and does not push to the branch: for each component whose version has no tag yet, it creates the annotated tag (`vX.Y.Z`, or `<subdir>/vX.Y.Z`) at the landed commit, pushes the tags, and creates the GitHub release for each; when every version is already tagged at this commit or an ancestor it does nothing and exits 0. When a version to tag already has a tag at a commit that is not this one and the version file did not change in this merge, there is nothing to release; when the merge changed the version file to a version already tagged at another commit, it fails with a message naming the version, the commit that holds the tag and what to do. It does not create or move a `latest` tag. A manual run in this mode releases the current commit the same way (the bump inputs do not apply and are refused with a reason). `git-semver released` reports what was tagged at the commit, as before. The commit-message rules (`chore: bump version`, `chore: install`) are not needed in this mode and are not consulted.

- git-semver's own repository releases this way — **gsv-bbc9.3** (blocked by gsv-bbc9.1 and gsv-bbc9.2)
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `.vendored/configs/git-semver.json`, `.vendored/configs/git-cicd.json`, generated `.github/workflows/git-cicd-*.yml` if they change, `VERSION`, `README.md`, `AGENTS.md`, `docs/`
  - shape: The repository's git-semver config selects the new mode. Its git-cicd config gains an `open` job for pull requests into `main` whose step is the version check from this repository's root `git-semver`, and the `release` job keeps running the root `release`. `VERSION` is bumped in this unit's own work so that the integration branch carries a version higher than `main`'s, making the pull request into `main` the first release done this way. `README.md` describes both ways a repository can release (bump on merge, the default install; bump in the pull request with git-cicd), what each needs from branch protection, and that the `latest` tag is not moved on the new path; the bootstrap instructions stop relying on a `latest` tag. `AGENTS.md` says that a change to a configured file bumps the version in the same pull request, and with which command.

## Acceptance criteria

- The check passes with no configured file changed; fails with a configured file changed and the version unchanged, lower or malformed, printing the fixing command; passes with any increase (patch, minor, major); handles a subdirectory component; tests show each, with no network.
- In the new mode, a merge whose version is untagged produces exactly the tag at the landed commit and one GitHub release call, and no push to the branch; a second run at the same commit does nothing; a version already tagged elsewhere fails with the stated message; no `latest` tag is created or moved; tests show each, with `git push` and `gh` replaced at the boundary the existing tests use.
- With the default config, `release` with no subcommand, `release bump` and `release publish` behave exactly as before; the existing tests pass unmodified, or any change to them is explained.
- `.vendored/pkg/git-cicd/git-cicd validate` reports the version check job; `verify` passes; `.vendored/pkg/git-cicd/git-cicd check --setup` passes with coverage at 99% or more for both scripts.
- The pull request into `plan/git-dev-883c` has a passing `Verdict / git-cicd:verdict`, and the integration branch's `VERSION` is higher than `main`'s.
- `install.sh` and `templates/github/workflows/version-bump.yml` are unchanged.
- `python3 .vendored/check --base origin/plan/git-dev-883c` reports nothing.

## Out of scope

- Pushing the bump to a pull request's branch for the author.
- Deleting the existing `latest` tag from the remote (an owner step), marking a release as defective, or anything else about how versions move.
- Changing what `install.sh` installs, or migrating git-cicd, git-vendored or any other repository (units 12 and 13 of the plan).
- Replacing `gh release create` with a platform adapter.

## Issues

| Issue | Scope |
|---|---|
| gsv-bbc9.1 | `git-semver check-bump` subcommand, its tests, README command entry |
| gsv-bbc9.2 | `bump_on: pull_request` mode in `release` (tag landed commit, push tags only, one `gh release create` per new tag, refuse duplicate version, no `latest`), schema + README key, tests |
| gsv-bbc9.3 | This repo: config selects the mode, `version-check` open job, regenerated workflows, VERSION 0.0.16 → 0.1.0, README/AGENTS.md release docs, bootstrap URL off `latest` (blocked by .1 and .2) |

## Refinement decisions

- **Subcommand name `check-bump`** (gsv-bbc9.1): it sits next to `check` and leaves `check`'s meaning as it is (exit 0 = a bump is needed).
- **`--base`/`--head` arguments win over `CICD_BASE`/`CICD_HEAD`; head defaults to HEAD** (gsv-bbc9.1): this is the usual CLI order, and CI passes no arguments, so it still uses the env vars as the doc asks.
- **Compare against the version at `<base>` (the target branch tip) and take changed files as `<base>...<head>`** (gsv-bbc9.1): the doc says the version must be higher than the target branch's, and git-cicd's `changed_files` uses a three-dot diff.
- **A component with no `files` is skipped, not an error** (gsv-bbc9.1): a check step must not fail on a component that has nothing configured.
- **Mode setting is a top-level `"bump_on": "merge" | "pull_request"` (default `merge`) in `.vendored/configs/git-semver.json`, and `release` reads it from git-semver's config path, not `.semver/config.json`** (gsv-bbc9.2): the doc puts the mode in the git-semver config and its schema, and `release`'s own `CONFIG_PATH` only holds the `install` settings.
- **Push each new tag by name, without `--force`** (gsv-bbc9.2): `--tags --force` would overwrite a tag held at another commit, the case the doc says must fail loudly.
- **Check every component before creating any tag** (gsv-bbc9.2): if the run fails on a duplicate version, it leaves no partial tags behind.
- **Treat a missing or all-zero base as "version file changed"** (gsv-bbc9.2): that is the safe choice, because a version already tagged elsewhere then fails instead of passing silently.
- **A manual run is refused when any bump input is non-empty** (gsv-bbc9.2) **and this repo's `release` job drops its `inputs`** (gsv-bbc9.3): git-cicd passes declared inputs with their defaults (`bump_type=patch`), so the inputs have to go before a manual run can proceed.
- **The `version-check` job runs only on PRs into `main` and uses the root `git-semver`** (gsv-bbc9.3): the doc limits the check to release branches, and the root script means the check runs the branch's own code, as the root `release` already does.
- **Bump VERSION from 0.0.16 to 0.1.0 (minor)** (gsv-bbc9.3): the release model changes, which counts as a feature, and any increase satisfies the check.
- **The bootstrap curl URL uses `main` instead of `latest`** (gsv-bbc9.3): the doc drops `latest`, and `install.sh` must not change.
