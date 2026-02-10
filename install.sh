#!/bin/bash
# git-semver/install.sh - Install or update git-semver in a project
#
# Usage:
#   install.sh <version>
#
# Environment:
#   GH_TOKEN - Used for gh api downloads (required for private repos).
#              Falls back to curl for public repos when not set.
#
# Behavior:
#   - Always updates: .semver/git-semver (core script), .semver/.version
#   - First install only: workflow template to .github/workflows/ (version-bump; skipped if present)
#   - Preserves .semver/config.json (only creates if missing)
#
set -euo pipefail

VERSION="${1:?Usage: install.sh <version>}"
SEMVER_REPO="mangimangi/git-semver"

# File download helper - uses gh api when GH_TOKEN is set, curl otherwise
fetch_file() {
    local repo_path="$1"
    local dest="$2"
    local ref="${3:-v$VERSION}"

    if [ -n "${GH_TOKEN:-}" ] && command -v gh &>/dev/null; then
        gh api "repos/$SEMVER_REPO/contents/$repo_path?ref=$ref" --jq '.content' | base64 -d > "$dest"
    else
        local base="https://raw.githubusercontent.com/$SEMVER_REPO"
        curl -fsSL "$base/$ref/$repo_path" -o "$dest"
    fi
}

echo "Installing git-semver v$VERSION from $SEMVER_REPO"

# Create directories
mkdir -p .semver .github/workflows

# Download core scripts
echo "Downloading git-semver..."
fetch_file "git-semver" ".semver/git-semver"
chmod +x .semver/git-semver
fetch_file "bump-and-release" ".semver/bump-and-release"
chmod +x .semver/bump-and-release
echo "$VERSION" > .semver/.version
echo "Installed git-semver v$VERSION"

# config.json - only create if missing (preserves user settings)
if [ ! -f .semver/config.json ]; then
    fetch_file "templates/semver/config.json" ".semver/config.json"
    echo "Created .semver/config.json (configure your file patterns!)"
fi

# Helper to install a workflow file (first install only)
install_workflow() {
    local workflow="$1"
    if [ -f ".github/workflows/$workflow" ]; then
        echo "Workflow .github/workflows/$workflow already exists, skipping"
        return
    fi
    if fetch_file "templates/github/workflows/$workflow" ".github/workflows/$workflow" 2>/dev/null; then
        echo "Installed .github/workflows/$workflow"
    fi
}

# Install workflow template (skipped if already present)
install_workflow "version-bump.yml"

# Register with git-vendored if present
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

echo ""
echo "Done! git-semver v$VERSION installed."
