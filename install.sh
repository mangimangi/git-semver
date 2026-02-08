#!/bin/bash
# git-semver/install.sh - Install or update git-semver in a project
#
# Usage:
#   install.sh <version> <semver_repo>
#
# Environment:
#   GH_TOKEN - Used for gh api downloads (required for private repos).
#              Falls back to curl for public repos when not set.
#
# Behavior:
#   - Downloads git-semver core script to .semver/git-semver
#   - Downloads workflow templates to .github/workflows/
#   - Writes .semver/.version for version tracking
#   - Preserves .semver/config.json (only creates if missing)
#   - Substitutes SEMVER_REPO placeholder in workflow templates
#   - Templates schedule cron from config (or removes schedule block)
#
# Install config (in .semver/config.json):
#   install.schedule    - Cron expression (default: "0 9 * * 1"), or false to disable
#
set -euo pipefail

VERSION="${1:?Usage: install.sh <version> <semver_repo>}"
SEMVER_REPO="${2:?Usage: install.sh <version> <semver_repo>}"

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

# Download core script
echo "Downloading git-semver..."
fetch_file "git-semver" ".semver/git-semver"
chmod +x .semver/git-semver
echo "$VERSION" > .semver/.version
echo "Installed git-semver v$VERSION"

# Read install config from existing config.json
INSTALL_SCHEDULE="0 9 * * 1"
if [ -f .semver/config.json ]; then
    INSTALL_SCHEDULE=$(python3 -c "
import json
c = json.load(open('.semver/config.json'))
v = c.get('install', {}).get('schedule', '0 9 * * 1')
if v is False: print('false')
else: print(v)
" 2>/dev/null || echo "0 9 * * 1")
fi

# Validate cron expression (warn but don't fail)
if [ "$INSTALL_SCHEDULE" != "false" ]; then
    FIELD_COUNT=$(echo "$INSTALL_SCHEDULE" | awk '{print NF}')
    if [ "$FIELD_COUNT" -ne 5 ]; then
        echo "Warning: install.schedule '$INSTALL_SCHEDULE' does not look like a valid cron expression (expected 5 fields, got $FIELD_COUNT)"
    fi
fi

# config.json - only create if missing (preserves user settings)
if [ ! -f .semver/config.json ]; then
    cat > .semver/config.json << 'DEFAULT_CONFIG'
{
  "version_file": "VERSION",
  "files": [
    "CHANGEME"
  ],
  "updates": {},
  "changelog": true
}
DEFAULT_CONFIG
    echo "Created .semver/config.json (configure your file patterns!)"
fi

# Helper to install a workflow file with placeholder substitution
install_workflow() {
    local workflow="$1"
    if fetch_file "templates/github/workflows/$workflow" ".github/workflows/$workflow" 2>/dev/null; then
        sed -i "s|SEMVER_REPO: USER/git-semver|SEMVER_REPO: $SEMVER_REPO|g" ".github/workflows/$workflow"
        # Substitute or remove schedule in install-git-semver.yml
        if [ "$INSTALL_SCHEDULE" = "false" ]; then
            sed -i '/^  schedule:$/d; /INSTALL_SCHEDULE/d' ".github/workflows/$workflow"
        else
            sed -i "s|INSTALL_SCHEDULE|$INSTALL_SCHEDULE|g" ".github/workflows/$workflow"
        fi
        echo "Updated .github/workflows/$workflow"
    fi
}

# Install workflow templates
install_workflow "version-bump.yml"
install_workflow "is-version-bump.yml"
install_workflow "install-git-semver.yml"

echo ""
echo "Done! git-semver v$VERSION installed."
