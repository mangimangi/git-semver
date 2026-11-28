# Local git-cicd check fails vendor-check on an integration-branch stack

> Captured: 2026-11-28

## What was happening

Implementing gsv-81b6 on `gsv-81b6/impl` (stacked on `plan/git-dev-883c`). Running `.vendored/pkg/git-cicd/git-cicd check --setup` (also with `--target plan/git-dev-883c`) reported `Vendor Check / git-semver:vendor-check failed` with "Protected vendor files were modified!" listing `.vendored/manifests/git-cicd.*`, `.vendored/pkg/git-cicd/git-cicd` and its templates — files nobody touched on this branch; they differ only from `origin/main`. `python3 .vendored/check --base origin/plan/git-dev-883c` reported nothing.

## Headache

Local 'git-cicd check' fails vendor-check on an integration-branch stack: .vendored/check defaults its base to origin/main (only GITHUB_BASE_REF overrides), ignoring git-cicd's --target / CICD_TARGET_BRANCH, so vendored git-cicd files that differ from main are reported as violations. Workaround: GITHUB_BASE_REF=plan/git-dev-883c git-cicd check --target plan/git-dev-883c. Fix idea: .vendored/check could fall back to origin/$CICD_TARGET_BRANCH.
