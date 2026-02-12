#!/bin/bash
# git-semver/install.sh - Install or update git-semver in a project
#
# Usage:
#   install.sh <version>
#
# Environment:
#   VENDOR_REF        - Version to install (falls back to positional $1)
#   VENDOR_REPO       - Source repo (falls back to mangimangi/git-semver)
#   VENDOR_INSTALL_DIR - Where to install code files (falls back to .semver/)
#   VENDOR_MANIFEST   - Path to write installed file manifest (optional)
#   GH_TOKEN          - Used for gh api downloads (required for private repos).
#                        Falls back to curl for public repos when not set.
#
# Behavior:
#   - Always updates: git-semver (core script), bump-and-release
#   - First install only: workflow template to .github/workflows/ (version-bump; skipped if present)
#   - Preserves .semver/config.json (only creates if missing)
#
set -euo pipefail

VERSION="${VENDOR_REF:-${1:?Usage: install.sh <version>}}"
SEMVER_REPO="${VENDOR_REPO:-mangimangi/git-semver}"
INSTALL_DIR="${VENDOR_INSTALL_DIR:-.semver}"

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

INSTALLED_FILES=()

# Create directories
mkdir -p "$INSTALL_DIR" .semver .github/workflows

# Download core scripts
echo "Downloading git-semver..."
fetch_file "git-semver" "$INSTALL_DIR/git-semver"
chmod +x "$INSTALL_DIR/git-semver"
INSTALLED_FILES+=("$INSTALL_DIR/git-semver")

fetch_file "bump-and-release" "$INSTALL_DIR/bump-and-release"
chmod +x "$INSTALL_DIR/bump-and-release"
INSTALLED_FILES+=("$INSTALL_DIR/bump-and-release")

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
        INSTALLED_FILES+=(".github/workflows/$workflow")
        echo "Installed .github/workflows/$workflow"
    fi
}

# Install workflow template (skipped if already present)
install_workflow "version-bump.yml"

# Write manifest when requested by the framework
if [ -n "${VENDOR_MANIFEST:-}" ]; then
    printf '%s\n' "${INSTALLED_FILES[@]}" > "$VENDOR_MANIFEST"
fi

echo ""
echo "Done! git-semver v$VERSION installed."
