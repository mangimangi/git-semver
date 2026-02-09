# git-vendored — Unified Vendor Management

*Absorbs the original git-block (vendor file protection) scope and adds unified
install + dogfood capabilities.*

## Problem

Every vendored tool (pearls, git-semver) ships its own bespoke workflows:

- **Install workflows** — `install-pearls.yml` (129 lines), `install-git-semver.yml`
  (125 lines). Same pattern, different hardcoded values.
- **Protection workflows** — `check-pearls-impl.yml` (211 lines). Tool-specific
  bash that knows about specific directories, allowed files, config flags.
- **Dogfood workflows** — `install-on-release.yml` (26 lines). Hardcoded to one
  vendor.

When a new tool is vendored, it needs its own copy of each. This doesn't scale.

## Solution

Two new tools, developed as directories in this repo (extractable to own repos):

- **git-vendored** — config-driven install + protection for all vendors
- **git-dogfood** — bridges release events to vendor self-update

Together with git-semver they form the vendor lifecycle:

```
code change → version-bump → release → dogfood → install-vendored → PR → merge
              (git-semver)    (git-semver) (git-dogfood) (git-vendored)
```

## Design Principles

### Thin workflows, vendored scripts

Workflows are install-once, rarely updated. All logic lives in vendored scripts
(extensionless executables with `#!/usr/bin/env python3`) that are updated on
each install and can be tested independently.

```
Workflow (install-once, static):         Script (vendored, updatable):
┌──────────────────────────────┐        ┌──────────────────────────────┐
│ on: schedule/dispatch        │        │ .vendored/install            │
│ steps:                       │   →    │ .vendored/check              │
│   - checkout                 │        │ .dogfood/resolve             │
│   - python3 .vendored/install│        │                              │
│   - create PR from output    │        │ Testable. Updatable.         │
└──────────────────────────────┘        └──────────────────────────────┘
```

### Config is the source of truth

`.vendored/config.json` is the single registry for all vendors. Both install
and protection workflows read it. Install scripts register themselves by
editing this file directly (no CLI dependency).

### Zero per-vendor workflow files

One `install-vendored.yml` handles schedule, dispatch, and workflow_call for
all vendors. No `install-pearls.yml`, `install-git-semver.yml`, etc.

### Extensionless executables

Vendored scripts use no file extension, consistent with `git-semver`, `prl`.
All are `#!/usr/bin/env python3`, callable as `python3 .vendored/install` or
`./.vendored/install`.

## Config Schema

`.vendored/config.json`:

```json
{
  "vendors": {
    "<vendor-name>": {
      "repo": "<owner/repo>",
      "private": false,
      "install_branch": "<branch-prefix>",
      "automerge": true,
      "dogfood": false,
      "protected": ["<glob-pattern>", ...],
      "allowed": ["<glob-pattern>", ...]
    }
  }
}
```

Example for this repo:

```json
{
  "vendors": {
    "git-vendored": {
      "repo": "mangimangi/git-vendored",
      "install_branch": "chore/install-git-vendored",
      "protected": [
        ".vendored/**",
        ".github/workflows/install-vendored.yml",
        ".github/workflows/check-vendor.yml"
      ],
      "allowed": [".vendored/config.json", ".vendored/.version"]
    },
    "git-dogfood": {
      "repo": "mangimangi/git-dogfood",
      "install_branch": "chore/install-git-dogfood",
      "protected": [".dogfood/**", ".github/workflows/dogfood.yml"],
      "allowed": []
    },
    "git-semver": {
      "repo": "mangimangi/git-semver",
      "install_branch": "chore/install-git-semver",
      "dogfood": true,
      "protected": [".semver/**"],
      "allowed": [".semver/config.json", ".semver/.version"]
    },
    "pearls": {
      "repo": "mangimangi/pearls",
      "private": true,
      "install_branch": "chore/install-pearls",
      "automerge": true,
      "protected": [".pearls/**"],
      "allowed": [
        ".pearls/issues.jsonl",
        ".pearls/config.json",
        ".pearls/.prl-version",
        ".pearls/archive/*.jsonl"
      ]
    }
  }
}
```

## git-vendored

### Directory layout (in-tree, extractable to own repo)

```
git-vendored/
├── install.sh                              # Installs git-vendored
├── VERSION
├── vendored/
│   ├── install                             # Install/update logic (vendored script)
│   └── check                               # Protection check logic (vendored script)
├── templates/
│   ├── vendored/
│   │   └── config.json                     # Default empty config
│   └── github/workflows/
│       ├── install-vendored.yml            # Thin workflow (install-once)
│       └── check-vendor.yml               # Thin workflow (install-once)
└── tests/
    ├── test_install.py
    └── test_check.py
```

Consumer repo gets:

```
.vendored/
├── config.json                             # Editable — vendor registry
├── .version                                # Auto-managed
├── install                                 # Vendored script (don't edit)
└── check                                   # Vendored script (don't edit)
.github/workflows/
├── install-vendored.yml                    # Thin workflow (don't edit)
└── check-vendor.yml                        # Thin workflow (don't edit)
```

### install-vendored.yml (thin workflow)

Triggers: schedule (check all vendors), workflow_dispatch (one or all),
workflow_call (for dogfood callers).

```yaml
on:
  schedule: [{cron: '0 9 * * 1'}]
  workflow_dispatch:
    inputs:
      vendor: {description: 'Vendor to update (or "all")', default: 'all'}
      version: {description: 'Version to install', default: 'latest'}
  workflow_call:
    inputs:
      vendor: {type: string, required: true}
      version: {type: string, default: 'latest'}
    secrets:
      token: {required: false}
```

Steps: checkout, call `.vendored/install` with vendor + version args, create
PR from output. All logic in the vendored script.

### check-vendor.yml (thin workflow)

Triggers on PR. Steps: checkout, call `.vendored/check` which reads config,
inspects changed files, exits non-zero on violations.

```yaml
on:
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Check vendor files
        run: python3 .vendored/check
```

### .vendored/install (script)

The install script handles:

1. Read `.vendored/config.json` for vendor entry (repo, private flag)
2. Resolve target version (releases API, falls back to VERSION file)
3. Check if already at target version (skip if match)
4. Download vendor's `install.sh` from source repo and run it
5. Output structured result (version diff, changed files) for PR creation

### .vendored/check (script)

The check script handles (logic from gsv-2697 git-block design):

1. Read `.vendored/config.json` for all vendor entries
2. For each vendor, check if PR branch matches `install_branch` prefix (skip)
3. For each changed file, match against `protected` patterns
4. If matched, check against `allowed` patterns (pass if allowed)
5. Collect violations, report, exit non-zero if any

### Auth

- Public vendor repos: `GITHUB_TOKEN` (default, no setup needed)
- Private vendor repos (`"private": true`): `VENDOR_PAT` secret
  - Single PAT with `Contents:Read` on all private vendor source repos
  - No `Workflows:Write` needed (workflows are install-once)
- PR creation/automerge: `GITHUB_TOKEN` suffices (no workflow file changes)

### install.sh (git-vendored's own installer)

```
1. Create .vendored/ directory
2. Download .vendored/install and .vendored/check scripts
3. chmod +x both
4. Write .vendored/.version
5. Create .vendored/config.json if missing (empty vendors)
6. Install workflow templates (first install only, skip if present)
7. Register git-vendored as a vendor in .vendored/config.json
```

### How other vendors register

Each vendor's install.sh adds a registration step:

```bash
# Register with git-vendored if present
if [ -f .vendored/config.json ]; then
    python3 -c "
import json, sys
with open('.vendored/config.json') as f:
    config = json.load(f)
config.setdefault('vendors', {})
config['vendors']['my-tool'] = {
    'repo': 'owner/my-tool',
    'install_branch': 'chore/install-my-tool',
    'protected': ['.my-tool/**'],
    'allowed': ['.my-tool/config.json']
}
with open('.vendored/config.json', 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
"
fi
```

## git-dogfood

### Why it's its own tool

git-dogfood bridges two independent systems:

- **git-semver** — provides Release events (version-bump → tag → release)
- **git-vendored** — provides install-vendored (update a vendor to a version)

Neither should own the bridge. git-dogfood is vendorable via git-vendored
like any other tool.

### Directory layout (in-tree, extractable to own repo)

```
git-dogfood/
├── install.sh                              # Installs git-dogfood
├── VERSION
├── dogfood/
│   └── resolve                             # Resolve which vendor to dogfood
├── templates/
│   └── github/workflows/
│       └── dogfood.yml                     # Thin workflow (install-once)
└── tests/
    └── test_resolve.py
```

Consumer repo gets:

```
.dogfood/
├── .version                                # Auto-managed
└── resolve                                 # Vendored script (don't edit)
.github/workflows/
└── dogfood.yml                             # Thin workflow (don't edit)
```

### dogfood.yml (thin workflow)

Triggers after Release workflow completes. Calls `.dogfood/resolve` to find
which vendor has `dogfood: true`, then calls `install-vendored.yml`:

```yaml
on:
  workflow_run:
    workflows: ["Release"]
    types: [completed]

jobs:
  resolve:
    if: github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    outputs:
      vendor: ${{ steps.find.outputs.vendor }}
    steps:
      - uses: actions/checkout@v4
      - id: find
        run: python3 .dogfood/resolve >> $GITHUB_OUTPUT

  install:
    needs: resolve
    if: needs.resolve.outputs.vendor
    uses: ./.github/workflows/install-vendored.yml
    with:
      vendor: ${{ needs.resolve.outputs.vendor }}
      version: latest
```

### .dogfood/resolve (script)

Reads `.vendored/config.json`, finds the vendor with `"dogfood": true`,
outputs `vendor=<name>` in GITHUB_OUTPUT format.

### install.sh (git-dogfood's own installer)

```
1. Create .dogfood/ directory
2. Download .dogfood/resolve script
3. chmod +x
4. Write .dogfood/.version
5. Install dogfood.yml workflow (first install only)
6. Register git-dogfood in .vendored/config.json (if present)
```

### Dependencies

git-dogfood requires:

- **git-vendored** — for `install-vendored.yml` (the install mechanism)
- **git-semver** — for `release.yml` (the Release trigger)

Install order: git-vendored first, then git-semver, then git-dogfood.

## What This Replaces

| Current (per-vendor)         | Lines | Replaced by                   |
|------------------------------|-------|-------------------------------|
| `install-pearls.yml`         | 129   | `install-vendored.yml` + `.vendored/install` |
| `install-git-semver.yml`     | 125   | `install-vendored.yml` + `.vendored/install` |
| `check-pearls-impl.yml`      | 211   | `check-vendor.yml` + `.vendored/check`       |
| `install-on-release.yml`     | 26    | `dogfood.yml` + `.dogfood/resolve`            |

Total: 491 lines of bespoke workflows → 2 thin workflows + 3 vendored scripts.

## Migration Path

1. Implement git-vendored and git-dogfood as directories in git-semver repo
2. Install git-vendored to this repo (creates `.vendored/`, workflows)
3. Register existing vendors (pearls, git-semver) in `.vendored/config.json`
4. Install git-dogfood to this repo (creates `.dogfood/`, workflow)
5. Verify: install-vendored can update pearls and git-semver
6. Verify: check-vendor catches violations for all vendors
7. Verify: dogfood chain works (release → dogfood → install-vendored)
8. Remove: `install-pearls.yml`, `install-git-semver.yml`,
   `check-pearls-impl.yml`, `install-on-release.yml`
9. Extract `git-vendored/` and `git-dogfood/` to own repos when ready
