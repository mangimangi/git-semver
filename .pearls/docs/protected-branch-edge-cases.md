# Protected Branch Support — Edge Cases

Deferred from the main epic (gsv-14cf). Consider after the core implementation lands.

## Merge Queue Support

GitHub merge queues should work since the publish job triggers on the final merge commit. But untested — may need special handling if the merge queue creates intermediate commits or changes the commit message format.

## Tag Already Exists

`git tag -a vX.Y.Z` fails if the tag already exists (not at HEAD). Scenarios:
- Orphaned tag from a failed previous run
- Race condition between queued workflow runs

Options: skip if tag exists, or force-update. Version tags should be unique, so this likely indicates a bug. Surface a clear error rather than silently overwriting.

## Multiple Queued Bumps

The existing concurrency group (`push-to-main`, `cancel-in-progress: false`) queues runs. `sync_branch()` handles fast-forwarding. But with the two-phase flow:
- Bump PR merges trigger publish job
- If two bump PRs merge in quick succession, two publish jobs run
- Second publish may try to tag a version that was already tagged by the first

Likely fine if tag idempotency is handled (see above).
