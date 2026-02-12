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


def _run_install(tmp_path: Path, install_script: Path, version: str = "1.2.3",
                 env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the install script in a temporary project directory."""
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        ["bash", str(install_script), version],
        cwd=project,
        capture_output=True,
        text=True,
        env=run_env,
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
        assert (project / ".semver" / "config.json").exists()
        # .version file should NOT be created (v2 contract)
        assert not (project / ".semver" / ".version").exists()

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

    def test_always_updates_core_script(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        # Pre-create with old content
        semver_dir = project / ".semver"
        semver_dir.mkdir()
        (semver_dir / "git-semver").write_text("old script")

        result = subprocess.run(
            ["bash", str(script), "2.0.0"],
            cwd=project,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Core script should be updated
        assert (semver_dir / "git-semver").read_text() != "old script"


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


class TestV2EnvVars:
    """Tests for v2 contract environment variable support."""

    def test_vendor_ref_used_for_version(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script, version="ignored",
                              env={"VENDOR_REF": "3.0.0"})

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Installing git-semver v3.0.0" in result.stdout

    def test_vendor_ref_fallback_to_positional(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script, version="1.5.0")

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Installing git-semver v1.5.0" in result.stdout

    def test_vendor_repo_used_for_repo(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script,
                              env={"VENDOR_REPO": "myorg/my-semver"})

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "from myorg/my-semver" in result.stdout

    def test_vendor_repo_fallback_to_default(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "from mangimangi/git-semver" in result.stdout

    def test_vendor_install_dir_for_code_files(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)

        custom_dir = ".vendored/pkg/git-semver"
        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
            env={**os.environ, "VENDOR_INSTALL_DIR": custom_dir},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Code files go to custom dir
        assert (project / custom_dir / "git-semver").exists()
        assert (project / custom_dir / "bump-and-release").exists()
        # Config stays in .semver/
        assert (project / ".semver" / "config.json").exists()

    def test_vendor_install_dir_fallback_to_semver(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script)
        project = tmp_path / "project"

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Default: code files in .semver/
        assert (project / ".semver" / "git-semver").exists()
        assert (project / ".semver" / "bump-and-release").exists()

    def test_no_env_vars_backwards_compatible(self, tmp_path):
        """Works with no v2 env vars set (old framework / direct use)."""
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script, version="1.0.0")
        project = tmp_path / "project"

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (project / ".semver" / "git-semver").exists()
        assert (project / ".semver" / "bump-and-release").exists()
        assert (project / ".semver" / "config.json").exists()
        assert not (project / ".semver" / ".version").exists()


class TestV2Manifest:
    """Tests for VENDOR_MANIFEST emission."""

    def test_manifest_written_when_env_var_set(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)
        manifest_path = tmp_path / "manifest.txt"

        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
            env={**os.environ, "VENDOR_MANIFEST": str(manifest_path)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert manifest_path.exists()
        lines = manifest_path.read_text().strip().split("\n")
        # Should include code files and workflow (fresh install)
        assert ".semver/git-semver" in lines
        assert ".semver/bump-and-release" in lines
        assert ".github/workflows/version-bump.yml" in lines

    def test_manifest_not_written_when_env_var_unset(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        result = _run_install(tmp_path, script)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # No manifest file should exist anywhere
        project = tmp_path / "project"
        assert not list(project.glob("*manifest*"))

    def test_manifest_excludes_config(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)
        manifest_path = tmp_path / "manifest.txt"

        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
            env={**os.environ, "VENDOR_MANIFEST": str(manifest_path)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = manifest_path.read_text()
        assert "config.json" not in content

    def test_manifest_with_custom_install_dir(self, tmp_path):
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)
        manifest_path = tmp_path / "manifest.txt"

        custom_dir = ".vendored/pkg/git-semver"
        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
            env={**os.environ,
                 "VENDOR_INSTALL_DIR": custom_dir,
                 "VENDOR_MANIFEST": str(manifest_path)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        lines = manifest_path.read_text().strip().split("\n")
        assert f"{custom_dir}/git-semver" in lines
        assert f"{custom_dir}/bump-and-release" in lines

    def test_manifest_excludes_existing_workflow(self, tmp_path):
        """Workflow not in manifest when it already existed (wasn't installed)."""
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)
        manifest_path = tmp_path / "manifest.txt"

        # Pre-create workflow
        wf_dir = project / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "version-bump.yml").write_text("custom: true\n")

        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
            env={**os.environ, "VENDOR_MANIFEST": str(manifest_path)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = manifest_path.read_text()
        assert "version-bump.yml" not in content


class TestV2NoSelfRegistration:
    """Tests that self-registration block has been removed."""

    def test_no_vendored_config_modification(self, tmp_path):
        """install.sh should not modify .vendored/config.json."""
        script = _stub_install_sh(tmp_path)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)

        # Pre-create .vendored/config.json
        vendored_dir = project / ".vendored"
        vendored_dir.mkdir()
        original_content = '{"vendors": {}}\n'
        (vendored_dir / "config.json").write_text(original_content)

        result = subprocess.run(
            ["bash", str(script), "1.2.3"],
            cwd=project,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # .vendored/config.json should be unchanged
        assert (vendored_dir / "config.json").read_text() == original_content
        assert "Registered git-semver" not in result.stdout

    def test_no_self_registration_code_in_script(self, tmp_path):
        """The install.sh source should not contain self-registration code."""
        content = INSTALL_SH.read_text()
        assert ".vendored/config.json" not in content
        assert "Registered git-semver" not in content
