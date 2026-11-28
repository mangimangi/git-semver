# git-semver: the version check raises the version and pushes it

> Unit 2 of plan `git-dev-aef7` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-aef7.md`; the policy is in `mangimangi/git-dev`, `.pearls/docs/what-reaches-main-policy.md`). Agreed with the owner on 2026-11-28. Delivers into `plan/git-dev-aef7`. Re-check every code reference against the code before using it.

## Problem

With `"bump_on": "pull_request"` a pull request into a release branch carries its own version bump, and merging it tags the merged commit. The check that guards it, `git-semver check-bump` (`cmd_check_bump`, `git-semver` line 570; parser at line 861), only fails and prints the command to run. So every pull request into `main` needs its author, or the session that wrote it, to remember the bump, and after another pull request merges the bump has to be made again.

The owner, 2026-11-28: "the version bumps should feel seamless", and on this point: "I think we should actually default to pushing the version update tbh".

## What already was decided (do not reopen)

- **Pushed by default.** In the pull request mode, when a change to a configured file comes without a higher version, the check raises the version and pushes the commit to the pull request's branch. A documented setting turns that off (check only, as today).
- **Any bump the author made stands.** If the version is already higher than the base's, by any amount, nothing is changed: a minor or major bump stays a person's decision. The pushed bump is a patch.
- **The push uses `CICD_WRITE_TOKEN`.** A push made with a workflow's own token starts no workflow, which would leave the pushed commit without checks. git-cicd gives a job a secret only if the job declares it (unit 1 of the plan), so in CI this token is present only for a job that asked for it. Without it (a fork, no secret, no declaration) nothing is pushed and the check fails naming the command, as today.
- **Where it may push.** Only to the pull request's source branch, only when that branch is in this repository, never to the release branch.
- The owner's way of working keeps this rare: work is merged into an integration branch and that branch into `main` once, so the bump is normally pushed once, onto the integration branch.
- The token value is never printed. No test reads a token from the environment.
- `release bump`, `release publish`, the default bump-on-merge behaviour, `install.sh` and `templates/github/workflows/version-bump.yml` do not change.
- Coverage: the `test` job fails below 99% for `git-semver` and `release`; shell changes come with bats tests. No vendor-protected file is added, changed or deleted; run `python3 .vendored/check --base origin/plan/git-dev-aef7` before finishing. The version is raised in the unit's own work, as the `version-check` job requires.

## What ships

- The check can raise the version itself
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `git-semver` (`cmd_check_bump` line 570, `cmd_bump` and `bump_component`, the parser at line 861), `templates/config.schema`, `tests/`
  - shape: The version check gains a fixing mode. For the root and for each configured component whose configured files changed without a higher version than the base's, it raises the version by a patch, applies `updates`, writes the changelog entry the way `bump` does, and makes one commit whose message says which components were raised and from what to what. A component whose version is already higher is left alone; a version that went down or is malformed is an error, not something to fix. With nothing to fix it makes no commit. It needs only the local repository. The mode is chosen by the repository's config (default on with `"bump_on": "pull_request"`, with a documented setting for check only) and can be forced either way by an argument.

- The fix is pushed to the pull request's branch, safely
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `git-semver` or `release` (whichever owns pushing; `release` documents its tokens at lines 55-56), `tests/`
  - shape: After a fixing commit, the check pushes it to the pull request's source branch, taken from git-cicd's variables (`CICD_SOURCE_BRANCH`, with `CICD_TARGET_BRANCH`, `CICD_BASE`, `CICD_HEAD`) when set and from arguments otherwise. It pushes only with `CICD_WRITE_TOKEN`, given to git for that one push in a way that leaves it out of the repository's config, the process list and every message. It refuses, with a reason and without pushing, when the source branch is the target branch, is a release branch, does not exist on this repository's remote, or has moved on from the commit under test. When it pushed, it exits in a way that does not record a pass for the commit that lacked the bump, and says that the pushed commit's own run is the one to wait for. When it cannot push (no token; a refusal above) it fails exactly as the check does today, naming the command to run. Tests cover every branch of that decision with `git push` replaced at the boundary the existing tests use.

- The suite cannot read a real token; the docs say how the bump happens
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `tests/conftest.py`, `tests/bats/` helpers, `README.md` (the pull request mode, tokens), `AGENTS.md`, `CHANGELOG.md`, `VERSION`
  - shape: The suite removes `CICD_WRITE_TOKEN`, `CICD_READ_TOKEN`, `VENDOR_PAT`, `GH_TOKEN` and `GITHUB_TOKEN` from the environment before every test, in one place for pytest and one for bats, and a test fails if that guard is removed; the suite passes with real-looking values exported for all five outside it. (In `mangimangi/git-vendored` a test that picked up the repository's real token printed a shortened form of it in a public log.) The README describes the pull request mode as it now is: what gets pushed, when nothing is, which token it needs and which permission that token needs, how to turn pushing off, and the job declaration a repository on git-cicd needs for it (`"secrets": ["CICD_WRITE_TOKEN"]` on the version check job, as git-cicd's README defines it). This repository's own git-cicd config is left for the adoption unit: its version check job gets the declaration only when git-cicd with declarations is installed here. `VERSION` is raised with its changelog entry.

## Acceptance criteria

- A change to a configured file without a bump: one commit raises the version by a patch with `updates` and the changelog applied, is pushed to the source branch with the write token, and the run does not record a pass for the old commit; shown by tests.
- A change with any bump already made: no commit, no push, pass.
- No token, a fork, or pushing turned off: no commit is pushed, and the check fails naming the command.
- It refuses to push to the target branch, a release branch, a branch not on this remote, and a branch that moved on; each with a reason.
- The token appears in no output, no commit, no git config left behind; a test asserts on the captured output.
- The token guard exists for pytest and bats, with the test that fails without it.
- `.vendored/pkg/git-cicd/git-cicd check --setup` passes with coverage at 99% or more for both scripts; `git-semver check-bump` passes against `origin/main`.
- The pull request into `plan/git-dev-aef7` has a passing `Verdict / git-cicd:verdict`.
- `python3 .vendored/check --base origin/plan/git-dev-aef7` reports nothing.

## Out of scope

- This repository's own job declaration and any change in git-cicd or git-vendored (units 1, 3 and 4 of the plan).
- Raising a version by more than a patch automatically; choosing the bump from commit messages.
- Marking a release as defective; anything else about how versions move.
