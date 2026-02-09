#!/bin/bash
# git-dogfood/install.sh - Install or update git-dogfood in a project
#
# Usage:
#   install.sh <version> [<repo>]
#
# Environment:
#   GH_TOKEN - Used for gh api downloads (required for private repos).
#              Falls back to curl for public repos when not set.
#
# Behavior:
#   - Always updates: .dogfood/resolve, .dogfood/.version
#   - First install only: dogfood.yml workflow (skipped if present)
#   - Registers git-dogfood in .vendored/config.json (if present)
#
# Prerequisites:
#   - git-vendored must be installed (.vendored/config.json must exist)
#   - git-semver must be installed (release.yml workflow must exist)
#
set -euo pipefail

VERSION="${1:?Usage: install.sh <version> [<repo>]}"
DOGFOOD_REPO="${2:-mangimangi/git-dogfood}"

# File download helper - uses gh api when GH_TOKEN is set, curl otherwise
fetch_file() {
    local repo_path="$1"
    local dest="$2"
    local ref="${3:-v$VERSION}"

    if [ -n "${GH_TOKEN:-}" ] && command -v gh &>/dev/null; then
        gh api "repos/$DOGFOOD_REPO/contents/$repo_path?ref=$ref" --jq '.content' | base64 -d > "$dest"
    else
        local base="https://raw.githubusercontent.com/$DOGFOOD_REPO"
        curl -fsSL "$base/$ref/$repo_path" -o "$dest"
    fi
}

echo "Installing git-dogfood v$VERSION from $DOGFOOD_REPO"

# Create directories
mkdir -p .dogfood .github/workflows

# Download resolve script
echo "Downloading .dogfood/resolve..."
fetch_file "dogfood/resolve" ".dogfood/resolve"
chmod +x .dogfood/resolve

# Write version
echo "$VERSION" > .dogfood/.version
echo "Installed git-dogfood v$VERSION"

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
install_workflow "dogfood.yml"

# Register git-dogfood in .vendored/config.json (if present)
if [ -f .vendored/config.json ]; then
    python3 -c "
import json
with open('.vendored/config.json') as f:
    config = json.load(f)
config.setdefault('vendors', {})
config['vendors']['git-dogfood'] = {
    'repo': '$DOGFOOD_REPO',
    'install_branch': 'chore/install-git-dogfood',
    'protected': ['.dogfood/**', '.github/workflows/dogfood.yml'],
    'allowed': ['.dogfood/.version']
}
with open('.vendored/config.json', 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
"
    echo "Registered git-dogfood in .vendored/config.json"
fi

echo ""
echo "Done! git-dogfood v$VERSION installed."
