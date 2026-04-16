#!/bin/bash
# git-semver/install.sh - Install or update git-semver in a project
#
# Usage:
#   install.sh <version>
#
# Environment:
#   VENDOR_REF        - Version to install (falls back to positional $1)
#   VENDOR_REPO       - Source repo (falls back to mangimangi/git-semver)
#   VENDOR_INSTALL_DIR - Where to install code files
#   VENDOR_MANIFEST   - Path to write installed file manifest (optional)
#   GH_TOKEN          - Used for gh api downloads (required for private repos).
#                        Falls back to curl for public repos when not set.
#
# Behavior:
#   - Always updates: git-semver (core script), release
#   - First install only: workflow template to .github/workflows/ (version-bump; skipped if present)
#   - Preserves .vendored/configs/git-semver.json (only creates if missing)
#
set -euo pipefail

VERSION="${VENDOR_REF:-${1:?Usage: install.sh <version>}}"
VERSION="${VERSION#v}"  # strip v prefix if present (VENDOR_REF includes it)
SEMVER_REPO="${VENDOR_REPO:-mangimangi/git-semver}"
INSTALL_DIR="${VENDOR_INSTALL_DIR:?VENDOR_INSTALL_DIR is required}"

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
mkdir -p "$INSTALL_DIR" .vendored/configs .github/workflows

# Download core scripts
echo "Downloading git-semver..."
fetch_file "git-semver" "$INSTALL_DIR/git-semver"
chmod +x "$INSTALL_DIR/git-semver"
INSTALLED_FILES+=("$INSTALL_DIR/git-semver")

fetch_file "release" "$INSTALL_DIR/release"
chmod +x "$INSTALL_DIR/release"
INSTALLED_FILES+=("$INSTALL_DIR/release")

# Clean up old script names from prior versions
rm -f "$INSTALL_DIR/bump-and-release" "$INSTALL_DIR/semver"

echo "Installed git-semver v$VERSION"

# config - only create if missing (preserves user settings)
if [ ! -f .vendored/configs/git-semver.json ]; then
    fetch_file "templates/semver/config.json" ".vendored/configs/git-semver.json"
    echo "Created .vendored/configs/git-semver.json (configure your file patterns!)"
fi

# Install config schema for vendor audit validation
mkdir -p .vendored/manifests
fetch_file "templates/config.schema" ".vendored/manifests/git-semver.schema"
INSTALLED_FILES+=(".vendored/manifests/git-semver.schema")

# Helper to install a workflow file (first install only).
# Substitutes __INSTALL_DIR__ with VENDOR_INSTALL_DIR so the workflow's `run:`
# paths match where release scripts were actually installed.
install_workflow() {
    local workflow="$1"
    local dest=".github/workflows/$workflow"
    if [ -f "$dest" ]; then
        echo "Workflow $dest already exists, skipping"
        return
    fi
    if fetch_file "templates/github/workflows/$workflow" "$dest" 2>/dev/null; then
        local tmp
        tmp="$(mktemp)"
        sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$dest" > "$tmp"
        mv "$tmp" "$dest"
        INSTALLED_FILES+=("$dest")
        echo "Installed $dest"
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
