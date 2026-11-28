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
#   - First install only: workflow template to .github/workflows/ (version-bump).
#     Never on an upgrade (an earlier install is recorded), never when the file
#     is present, and never when the repository releases through git-cicd (its
#     git-cicd config runs git-semver's `release`, or its git-semver config sets
#     "bump_on": "pull_request").
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
WORKFLOW=.github/workflows/version-bump.yml
PREVIOUS_FILES=.vendored/manifests/git-semver.files

# Recorded before anything is written: an earlier git-semver install leaves its
# manifests or its scripts behind, so their absence means a first install.
EARLIER_INSTALL=
if [ -e .vendored/manifests/git-semver.version ] || [ -e "$PREVIOUS_FILES" ] \
   || [ -e "$INSTALL_DIR/git-semver" ] || [ -e .semver/git-semver ]; then
    EARLIER_INSTALL=1
fi

# The workflow was installed by an earlier git-semver install when that
# install's manifest lists it.
WORKFLOW_FROM_EARLIER=
if [ -f "$PREVIOUS_FILES" ] && grep -qxF "$WORKFLOW" "$PREVIOUS_FILES"; then
    WORKFLOW_FROM_EARLIER=1
fi

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

# Print why the repository releases through git-cicd, or nothing when it does
# not: a git-cicd job step that is git-semver's `release` (`release`,
# `./release`, `<install dir>/release`, `.semver/release` or a path ending in
# `git-semver/release`, alone or as the command of an argument list), or
# "bump_on": "pull_request" in the git-semver config. The JSON is flattened to
# one line and only its "steps" arrays (one level of nesting) are searched.
releases_through_git_cicd() {
    local cicd=.vendored/configs/git-cicd.json semver=.vendored/configs/git-semver.json
    local step
    if [ -f "$cicd" ]; then
        while IFS= read -r step; do
            case "$step" in
                release|./release|"$INSTALL_DIR/release"|.semver/release|*/git-semver/release)
                    echo "$cicd has a job step that runs git-semver's release"
                    return ;;
            esac
        done < <(tr -d '\n' < "$cicd" \
            | grep -oE '"steps"[[:space:]]*:[[:space:]]*\[([^][]|\[[^][]*\])*\]' \
            | sed -E 's/^"steps"[[:space:]]*:[[:space:]]*//; s/\[[[:space:]]*("[^"]*")[^][]*\]/\1/g' \
            | grep -oE '"[^"]*"' | tr -d '"')
    fi
    if [ -f "$semver" ] && tr -d '\n' < "$semver" \
        | grep -qE '"bump_on"[[:space:]]*:[[:space:]]*"pull_request"'; then
        echo "$semver sets \"bump_on\": \"pull_request\""
    fi
}

# Install the workflow on a first install only. Substitutes __INSTALL_DIR__
# with VENDOR_INSTALL_DIR so the workflow's `run:` paths match where release
# scripts were actually installed.
install_workflow() {
    local workflow="$1"
    local dest=".github/workflows/$workflow"
    local reason
    if [ -f "$dest" ]; then
        echo "Workflow $dest already exists, skipping"
        # Still git-semver's when an earlier install wrote it.
        if [ -n "$WORKFLOW_FROM_EARLIER" ]; then
            INSTALLED_FILES+=("$dest")
        fi
        return
    fi
    if [ -n "$EARLIER_INSTALL" ]; then
        echo "Not installing $dest: an upgrade never adds it (git-semver was installed here before)"
        return
    fi
    reason="$(releases_through_git_cicd)"
    if [ -n "$reason" ]; then
        echo "Not installing $dest: the repository releases through git-cicd ($reason)"
        return
    fi
    if fetch_file "templates/github/workflows/$workflow" "$dest" 2>/dev/null; then
        local tmp
        tmp="$(mktemp)"
        sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$dest" > "$tmp"
        mv "$tmp" "$dest"
        INSTALLED_FILES+=("$dest")
        echo "Installed $dest"
    else
        rm -f "$dest"
    fi
}

install_workflow "version-bump.yml"

# Write manifest when requested by the framework
# (only files that are on disk: the manifest never lists an absent file).
if [ -n "${VENDOR_MANIFEST:-}" ]; then
    : > "$VENDOR_MANIFEST.tmp"
    for f in "${INSTALLED_FILES[@]}"; do
        if [ -e "$f" ]; then
            printf '%s\n' "$f" >> "$VENDOR_MANIFEST.tmp"
        fi
    done
    mv "$VENDOR_MANIFEST.tmp" "$VENDOR_MANIFEST"
fi

echo ""
echo "Done! git-semver v$VERSION installed."
