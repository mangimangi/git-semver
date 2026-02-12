# Git-semver: Vendor V2 Compliance

Changes needed to make git-semver compliant with the git-vendored v2 contract.

## Summary

| Area | Status | Work needed |
|------|--------|-------------|
| `install.sh` env vars | non-compliant | Use `VENDOR_REF`/`VENDOR_REPO` instead of `$1` |
| `install.sh` install dir | non-compliant | Use `VENDOR_INSTALL_DIR` with `.semver/` fallback |
| `install.sh` manifest | non-compliant | Write all paths to `$VENDOR_MANIFEST` |
| `install.sh` version file | non-compliant | Remove `.semver/.version` write |
| `install.sh` self-registration | non-compliant | Remove `.vendored/config.json` write |
| `git-semver` config loading | non-compliant | Try `.vendored/configs/git-semver.json` first |

## install.sh changes

### 1. Environment variables

Replace positional arg with env vars (keep positional as fallback for old framework):

```bash
# Before
VERSION="${1:?Usage: install.sh <version>}"
SEMVER_REPO="mangimangi/git-semver"

# After
VERSION="${VENDOR_REF:-${1:?Usage: install.sh <version>}}"
SEMVER_REPO="${VENDOR_REPO:-mangimangi/git-semver}"
```

### 2. VENDOR_INSTALL_DIR

Add install dir resolution. Code files install under `$INSTALL_DIR`; config stays in `.semver/`.

```bash
INSTALL_DIR="${VENDOR_INSTALL_DIR:-.semver}"
```

Dogfood note: when git-semver is installed in its own repo, the framework infers dogfood from key/repo name matching and does not set `VENDOR_INSTALL_DIR`. The fallback to `.semver/` kicks in automatically.

### 3. File placement

Update fetch targets for code files to use `$INSTALL_DIR`:

| File | Before | After | Notes |
|------|--------|-------|-------|
| `git-semver` | `.semver/git-semver` | `$INSTALL_DIR/git-semver` | Code |
| `bump-and-release` | `.semver/bump-and-release` | `$INSTALL_DIR/bump-and-release` | Code |
| `version-bump.yml` | `.github/workflows/version-bump.yml` | `.github/workflows/version-bump.yml` | Workflow — fixed path |
| `config.json` | `.semver/config.json` | `.semver/config.json` | Create-only — stays |

Update the `mkdir` and `fetch_file` calls:

```bash
# Before
mkdir -p .semver .github/workflows
fetch_file "git-semver" ".semver/git-semver"
chmod +x .semver/git-semver
fetch_file "bump-and-release" ".semver/bump-and-release"
chmod +x .semver/bump-and-release

# After
mkdir -p "$INSTALL_DIR" .semver .github/workflows
fetch_file "git-semver" "$INSTALL_DIR/git-semver"
chmod +x "$INSTALL_DIR/git-semver"
fetch_file "bump-and-release" "$INSTALL_DIR/bump-and-release"
chmod +x "$INSTALL_DIR/bump-and-release"
```

Note: `mkdir -p .semver` is still needed for config.json creation (create-only, first install).

### 4. Remove version file write

Delete this line — the framework writes version to `.vendored/manifests/git-semver.version`:

```bash
# DELETE THIS LINE
echo "$VERSION" > .semver/.version
```

### 5. Remove self-registration

Delete the entire `.vendored/config.json` registration block. The framework handles vendor registration after `install.sh` runs:

```bash
# DELETE THIS ENTIRE BLOCK
if [ -f .vendored/config.json ]; then
    python3 -c "
import json
with open('.vendored/config.json') as f:
    config = json.load(f)
config.setdefault('vendors', {})
config['vendors']['git-semver'] = {
    'repo': '$SEMVER_REPO',
    'install_branch': 'chore/install-git-semver',
    'dogfood': True,
    'protected': ['.semver/**'],
    'allowed': ['.semver/config.json', '.semver/.version']
}
with open('.vendored/config.json', 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
"
    echo "Registered git-semver in .vendored/config.json"
fi
```

### 6. Manifest emission

Track every installed file and write to `$VENDOR_MANIFEST`:

```bash
INSTALLED_FILES=()

mkdir -p "$INSTALL_DIR" .semver .github/workflows

fetch_file "git-semver" "$INSTALL_DIR/git-semver"
chmod +x "$INSTALL_DIR/git-semver"
INSTALLED_FILES+=("$INSTALL_DIR/git-semver")

fetch_file "bump-and-release" "$INSTALL_DIR/bump-and-release"
chmod +x "$INSTALL_DIR/bump-and-release"
INSTALLED_FILES+=("$INSTALL_DIR/bump-and-release")

# Config (create-only, not in manifest — it's user-editable)
if [ ! -f .semver/config.json ]; then
    fetch_file "templates/semver/config.json" ".semver/config.json"
fi

# Workflow (first-install only, add to manifest if installed)
if [ ! -f ".github/workflows/version-bump.yml" ]; then
    if fetch_file "templates/github/workflows/version-bump.yml" ".github/workflows/version-bump.yml" 2>/dev/null; then
        INSTALLED_FILES+=(".github/workflows/version-bump.yml")
    fi
fi

# Write manifest
if [ -n "${VENDOR_MANIFEST:-}" ]; then
    printf '%s\n' "${INSTALLED_FILES[@]}" > "$VENDOR_MANIFEST"
fi
```

---

## git-semver runtime changes

### Config loading

Update `load_config()` to try the vendored config path first, filtering out the `_vendor` key:

```python
VENDORED_CONFIG = ".vendored/configs/git-semver.json"
DEFAULT_CONFIG_PATH = ".semver/config.json"

def load_config(config_path=None):
    """Load and validate config. Tries vendored path first."""
    if config_path:
        path = Path(config_path)
    else:
        vendored = Path(VENDORED_CONFIG)
        path = vendored if vendored.exists() else Path(DEFAULT_CONFIG_PATH)

    if not path.exists():
        raise SemverError(f"Config not found: {path}")

    with open(path) as f:
        raw = json.load(f)

    # Filter out framework-owned _vendor key
    config = {k: v for k, v in raw.items() if k != "_vendor"}
    # ... existing validation logic on config ...
    return config
```

The `--config` CLI flag still works as an explicit override (skips the vendored lookup).

---

## Backwards compatibility

| Scenario | Behavior |
|----------|----------|
| New framework | `VENDOR_INSTALL_DIR` set → code goes to `.vendored/pkg/git-semver/` |
| Old framework | Env vars unset → falls back to `.semver/`, no manifest written |
| Dogfood (self-install) | `VENDOR_INSTALL_DIR` not set → falls back to `.semver/` |

## Checklist

- [ ] `install.sh`: Use `VENDOR_REF`/`VENDOR_REPO` with positional fallback
- [ ] `install.sh`: Use `VENDOR_INSTALL_DIR` with `.semver/` fallback for code files
- [ ] `install.sh`: Track all files in `INSTALLED_FILES` array
- [ ] `install.sh`: Write `$VENDOR_MANIFEST` when set
- [ ] `install.sh`: Remove `.semver/.version` write
- [ ] `install.sh`: Remove `.vendored/config.json` self-registration block
- [ ] `git-semver`: Update `load_config()` to try vendored config first, filter `_vendor`
- [ ] Tests: Update for new file paths and env var contract
- [ ] Release: Tag new version
