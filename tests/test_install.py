"""Tests for install.sh."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
INSTALL_SH = ROOT / "install.sh"

# Template content that install.sh would fetch from the repo
TEMPLATE_VERSION_BUMP = (ROOT / "templates" / "github" / "workflows" / "version-bump.yml").read_text()
TEMPLATE_CONFIG = (ROOT / "templates" / "semver" / "config.json").read_text()
CORE_SCRIPT = (ROOT / "git-semver").read_text()
BUMP_AND_RELEASE = (ROOT / "bump-and-release").read_text()


def _stub_install_sh(tmp_path: Path) -> Path:
    """Create a modified install.sh that fetches from local files instead of GitHub.

    Replaces the fetch_file function with one that copies from a local
    'repo' directory, avoiding any network calls.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Populate the local repo mirror with template files
    (repo_dir / "git-semver").write_text(CORE_SCRIPT)
    (repo_dir / "bump-and-release").write_text(BUMP_AND_RELEASE)
    templates = repo_dir / "templates"
    (templates / "github" / "workflows").mkdir(parents=True)
    (templates / "github" / "workflows" / "version-bump.yml").write_text(TEMPLATE_VERSION_BUMP)
    (templates / "semver").mkdir(parents=True)
    (templates / "semver" / "config.json").write_text(TEMPLATE_CONFIG)

    # Read original install.sh and replace fetch_file with local copy
    original = INSTALL_SH.read_text()
    stub_fetch = f'''fetch_file() {{
    local repo_path="$1"
    local dest="$2"
    cp "{repo_dir}/$repo_path" "$dest"
}}'''
    # Replace the fetch_file function (from 'fetch_file()' to the closing '}')
    import re
    modified = re.sub(
        r'^fetch_file\(\) \{.*?^\}',
        stub_fetch,
        original,
        flags=re.MULTILINE | re.DOTALL,
    )
    stub_script = tmp_path / "install.sh"
    stub_script.write_text(modified)
    stub_script.chmod(0o755)
    return stub_script


def _run_install(tmp_path: Path, install_script: Path, version: str = "1.2.3") -> subprocess.CompletedProcess:
    """Run the install script in a temporary project directory."""
    project = tmp_path / "project"
    project.mkdir()
    return subprocess.run(
        ["bash", str(install_script), version],
        cwd=project,
        capture_output=True,
        text=True,
    )


class TestInstallFreshProject:
    """Tests for installing into a project with no prior git-semver."""

    def test_creates_semver_directory_and_files(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script)
        project = tmp_path / "project"

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (project / ".semver" / "git-semver").exists()
        assert (project / ".semver" / "bump-and-release").exists()
        assert (project / ".semver" / ".version").exists()
        assert (project / ".semver" / "config.json").exists()

    def test_version_file_contains_version(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        _run_install(tmp_path, script, version="2.0.0")
        project = tmp_path / "project"

        assert (project / ".semver" / ".version").read_text().strip() == "2.0.0"

    def test_core_script_is_executable(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        _run_install(tmp_path, script)
        project = tmp_path / "project"

        mode = (project / ".semver" / "git-semver").stat().st_mode
        assert mode & 0o111, "git-semver should be executable"

        mode = (project / ".semver" / "bump-and-release").stat().st_mode
        assert mode & 0o111, "bump-and-release should be executable"

    def test_installs_workflow_templates(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script)
        project = tmp_path / "project"

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (project / ".github" / "workflows" / "version-bump.yml").exists()

    def test_output_reports_success(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script, version="1.0.0")

        assert "Installing git-semver v1.0.0" in result.stdout
        assert "Installed git-semver v1.0.0" in result.stdout
        assert "Done! git-semver v1.0.0 installed." in result.stdout


class TestInstallExistingProject:
    """Tests for re-installing / upgrading when files already exist."""

    def test_skips_existing_workflows(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        # Pre-create workflow files with custom content
        wf_dir = project / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "version-bump.yml").write_text("custom: true\n")

        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Existing files should be preserved
        assert (wf_dir / "version-bump.yml").read_text() == "custom: true\n"
        assert "already exists, skipping" in result.stdout

    def test_preserves_existing_config(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        # Pre-create config
        semver_dir = project / ".semver"
        semver_dir.mkdir()
        (semver_dir / "config.json").write_text('{"files": ["src/**"]}\n')

        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (semver_dir / "config.json").read_text() == '{"files": ["src/**"]}\n'

    def test_always_updates_core_script_and_version(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        # Pre-create with old version
        semver_dir = project / ".semver"
        semver_dir.mkdir()
        (semver_dir / "git-semver").write_text("old script")
        (semver_dir / ".version").write_text("0.0.1")

        result = subprocess.run(
            ["bash", str(script), "2.0.0"],
            cwd=project,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Core script and version should be updated
        assert (semver_dir / "git-semver").read_text() != "old script"
        assert (semver_dir / ".version").read_text().strip() == "2.0.0"


class TestInstallUsage:
    """Tests for argument handling."""

    def test_fails_without_version_arg(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        result = subprocess.run(
            ["bash", str(script)],
            cwd=project,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "Usage:" in result.stderr
