# git-semver: release is one step

> Unit 4 of plan `git-dev-883c` (record: `mangimangi/git-dev`, `.pearls/docs/epics/git-dev-883c.md`). Agreed with the owner on 2026-11-28. Delivers into `plan/git-dev-883c`. Re-check every code reference against the code before using it.

## Problem

git-semver's release logic is split between a script and a workflow. `release` (259 lines) has two subcommands, `bump` (`cmd_bump`) and `publish` (`cmd_publish`), and `.github/workflows/version-bump.yml` ("Bump & Release") decides which to run with two jobs keyed on the head commit's message:

- job `bump`: on a manual run, or on a push to `main` whose head commit message starts with neither `chore: bump version` nor `chore: install`; runs `release bump`;
- job `publish`: on a push whose head commit message starts with `chore: bump version`; runs `release publish`;
- `contents: write`, `pull-requests: write`; concurrency group `push-to-main`, `cancel-in-progress: false`; checkout with `fetch-depth: 0`, `fetch-tags: true`; env `GH_TOKEN`, `GITHUB_EVENT_BEFORE`, `INPUT_BUMP_TYPE`, `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION`.

So part of how a release works lives in a workflow file, and a workflow file is the one thing an upgrade cannot deliver (an install pull request never carries workflow files). git-cicd v0.0.4, installed here (#94), executes `merge`, `cron` and manual runs with declared inputs, and has no ordering between jobs: bump then publish is one step in one job. git-cicd's own repository already releases this way, with the decision in a script of its own, `ci/release.sh` (`mangimangi/git-cicd`), which re-creates the workflow's commit-message rule and translates `CICD_` variables into the `GITHUB_EVENT_NAME`, `GITHUB_EVENT_BEFORE` and `INPUT_*` variables `release` reads. Every repository that moves its release onto git-cicd would have to copy that script. The decision belongs in git-semver.

What `release` does today, to keep (read from `release` on `main`, 2026-11-28):

- `handle_push_bump`: needs `GITHUB_EVENT_BEFORE`; `configure_git`, `sync_branch` (fast-forward to pick up bumps from queued runs), `git-semver bump-all --since <before> --no-push`; nothing more when no bump was needed; with `automerge: false` opens a pull request from `chore/bump-version-<time>`; otherwise `try_push_or_pr` (direct push, falling back to a pull request when the branch is protected), and when the direct push worked, `git-semver tag --push` and `create_releases` in the same run (a push made with the workflow's token starts no new run, so publish would never fire).
- `handle_dispatch_bump` (lines 175 on): bump type, subdirectory and changelog text from `INPUT_BUMP_TYPE` (default `patch`), `INPUT_SUBDIRECTORY`, `INPUT_CHANGELOG_DESCRIPTION`.
- `cmd_publish`: `configure_git`, `sync_branch`, `git-semver tag --push`, `create_releases` (a GitHub release per tag at HEAD, skipping `latest`).
- `read_config`: `install.on_merge` and `install.automerge`.

## What already was decided (do not reopen)

- Per-repository publishing (PyPI, container images) is not git-semver's business: it is the repository's own later step in the same job, for example `"steps": [".vendored/pkg/git-semver/release", "ci/publish-image.sh"]`. git-semver's "publish" stays "tag plus GitHub release". For that later step to work it must be able to tell whether this run released a version, and which.
- What `install.sh` installs into a consumer does not change in this unit: `version-bump.yml` still ships (`install.sh` line 95), and `bump` and `publish` keep working for every consumer still on it.
- The moving `latest` tag is unchanged in this unit (its removal is decided, for a later plan).
- The old `.github/workflows/version-bump.yml` in this repository is vendor-protected (`.vendored/configs/git-semver.json`, `_vendor.protected`). The sessions do not add, change or delete it; the planning session removes it from the integration branch after this unit, before the branch reaches `main`. Until then the old workflow and the new job both exist on the integration branch only; nothing on `main` changes.

## What ships

- `release` decides for itself: one entry point for a merge and a manual run
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `release` (`main`, `cmd_bump`, `cmd_publish`, `handle_push_bump`, `handle_dispatch_bump`), `tests/`, `README.md`, `docs/`
  - shape: A single way to call `release` (no `bump`/`publish` argument needed) works out which case it is in and does it. On a change that landed on a branch: the landed commit is a bump commit (message starts with `chore: bump version`): tag and create the releases, as `publish` does; the landed commit is an install commit (`chore: install`): nothing, exit 0; anything else: bump as `handle_push_bump` does, including `on_merge`, `automerge`, the protected-branch fallback and tagging in the same run when the direct push worked. On a manual run: bump as `handle_dispatch_bump` does. It reads which case it is in from git-cicd's variables when they are set (`CICD_TRIGGER` `merge` or `manual`, `CICD_BASE` as the commit before the push, `CICD_HEAD`) and from the GitHub Actions variables it reads today otherwise, so the same script serves a git-cicd job and `version-bump.yml`. Bump type, subdirectory and changelog text come from the declared inputs of a manual run (`CICD_INPUT_BUMP_TYPE`, `CICD_INPUT_SUBDIRECTORY`, `CICD_INPUT_CHANGELOG_DESCRIPTION`) when set, else from `INPUT_*` as today. `release bump` and `release publish` behave exactly as before. Any other trigger (`open`, `cron`) is refused with a reason and a non-zero exit. Tests cover each case without the network.

- A later step can ask what was released at this commit
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `git-semver` (a new read-only subcommand) or `release`, `tests/`, `README.md`
  - shape: A documented, read-only command prints the version or versions released at the current commit (the version tags pointing at it, never `latest`), one per line, and prints nothing and exits 0 when none was. It needs only the local repository, no token and no network, so a repository's own later step in the same job can use it to decide whether to publish (`ci/publish-image.sh`). The README shows that pattern with a job whose steps are git-semver's release and then the repository's own script, and says that with a protected branch the publish step sees a version on the run for the merged bump commit, not on the run that opened the bump pull request.

- git-semver's own release is a git-cicd job
  - vehicle: type: issue
  - source repo: git-semver
  - target repo: git-semver
  - affected surface: `.vendored/configs/git-cicd.json`, `ci/` (only if a wrapper is needed), generated `.github/workflows/git-cicd-*.yml`, `.vendored/configs/git-semver.json` (`files`), `README.md`, `AGENTS.md`
  - shape: The repository's config declares, beside `test` and `vendor-check`, a `release` job: on `merge` for `main`, and a manual run with `bump_type` (choices `patch`, `minor`, `major`; default `patch`), `subdirectory` and `changelog_description` as declared inputs, the way git-cicd's own config declares them. Its step runs this repository's own `release` at the repository root (as git-cicd's workflow runs its own root tool), not the vendored copy under `.vendored/pkg/git-semver/`, which does not have the new entry point until a release is installed back. `.vendored/pkg/git-cicd/git-cicd generate` is run and the generated `Merge` and `Manual` workflows are committed with `Open`; `verify` passes. `README.md` and `AGENTS.md` say how a release happens here and how to start one by hand (Actions tab, **Manual**, job `release`). The README section for adopters documents the `merge` job that replaces `version-bump.yml` for a repository that uses git-cicd, next to the existing workflow, which stays the default install.

## Acceptance criteria

- `release` with no subcommand does the right thing for each case above; the tests show each one, including "bump commit publishes", "install commit does nothing", "no configured file changed, no bump", `automerge: false`, and a manual run with each input.
- `release bump` and `release publish` are unchanged in behaviour; the existing tests pass unmodified, or any change to them is explained in the pull request.
- The command that reports what was released prints the version at a tagged commit and nothing at an untagged one, with no network.
- `.vendored/pkg/git-cicd/git-cicd validate` reports the `release` job; `verify` passes; `.vendored/pkg/git-cicd/git-cicd check --setup` passes.
- The pull request into `plan/git-dev-883c` has a passing `Verdict / git-cicd:verdict`.
- `install.sh` and `templates/github/workflows/version-bump.yml` are unchanged.
- `python3 .vendored/check --base origin/plan/git-dev-883c` reports nothing.

## Out of scope

- Deleting `.github/workflows/version-bump.yml` or `dogfood.yml` here (vendor-protected; done by the planning session).
- What `install.sh` installs into consumers; migrating any consumer.
- Removing the `latest` tag; marking a release as defective; anything else about how versions move.
- Replacing `gh pr create` and `gh release create` with a platform adapter.
- Any change in git-cicd or git-vendored.
