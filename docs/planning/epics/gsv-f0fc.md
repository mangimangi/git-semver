# vendor-config-validation: git-semver

> **Target repo:** mangimangi/git-semver
>
> **Parent epic:** mdci-0424 (vendor-config-validation)
>
> **Parent planning doc:** [vendor-config-validation.md](vendor-config-validation.md)
>
> **Session graph:** refine → [implement → eval]*
>
> **Blocked by:** git-vendored (schema framework must ship first)

## Context

git-semver is the versioning tool. Consumer repos install it via git-vendored and configure it through `.vendored/configs/git-semver.json`. This work adds a schema file declaring what config fields git-semver owns.

## Scope

### 1. Create `templates/config.schema`

Declare the config fields that git-semver owns. The git-vendored framework will install this to `.vendored/manifests/git-semver.schema` in consumer repos during vendor update.

**Known git-semver-owned fields:** Verify against source — git-semver's config surface needs to be inventoried during the refine session.

**Acceptance criteria:**
- `templates/config.schema` exists and follows the schema format
- All fields that git-semver reads from its config are declared
- No fields that belong to other vendors are included

## Schema format

```json
{
  "vendor": "git-semver",
  "fields": {
    "...": "to be determined during refine — inventory the config fields from source"
  }
}
```

Top-level fields only. The refine session should read git-semver's source to enumerate all config fields it reads.

## Cross-repo context

- git-vendored handles schema installation — git-semver just ships the file in `templates/`
- The schema format is defined by git-vendored (see vcv-git-vendored planning doc)
- Registry migration (`_vendor` → `.registry`) is handled by the git-vendored framework during vendor update
- git-semver already has a well-organized `templates/` directory — adding the schema file is a natural fit

## Not in scope

- Source layout alignment (separate follow-up epic)
- Changes to how git-semver reads its own config internally
