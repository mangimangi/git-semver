"""Tests for changelog update operations."""

from unittest.mock import MagicMock, patch

import git_semver


class TestUpdateChangelog:
    def test_adds_entry_to_existing(self, tmp_repo):
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0] - 2025-01-01\n\n- Initial\n")
        with patch.object(git_semver, "get_commits_since_tag", return_value=["feat: new feature"]):
            git_semver.update_changelog("CHANGELOG.md", "0.2.0")
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "## [0.2.0]" in content
        assert "- feat: new feature" in content
        # New entry should appear before old entry
        assert content.index("## [0.2.0]") < content.index("## [0.1.0]")

    def test_appends_when_no_existing_entries(self, tmp_repo):
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")
        with patch.object(git_semver, "get_commits_since_tag", return_value=["initial commit"]):
            git_semver.update_changelog("CHANGELOG.md", "0.1.0")
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "## [0.1.0]" in content
        assert "- initial commit" in content

    def test_with_description_override(self, tmp_repo):
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")
        git_semver.update_changelog("CHANGELOG.md", "0.1.0", description="Custom entry")
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "- Custom entry" in content

    def test_with_ignore_prefixes(self, tmp_repo):
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")
        commits = ["feat: new thing", "chore: bump deps", "docs: update readme"]
        with patch.object(git_semver, "get_commits_since_tag", return_value=commits):
            git_semver.update_changelog(
                "CHANGELOG.md", "0.1.0",
                ignore_prefixes=["chore:", "docs:"],
            )
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "feat: new thing" in content
        assert "chore: bump deps" not in content
        assert "docs: update readme" not in content

    def test_all_commits_filtered(self, tmp_repo):
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")
        commits = ["chore: bump deps"]
        with patch.object(git_semver, "get_commits_since_tag", return_value=commits):
            git_semver.update_changelog(
                "CHANGELOG.md", "0.1.0",
                ignore_prefixes=["chore:"],
            )
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "No notable changes" in content

    def test_missing_file_skipped(self, tmp_repo, capsys):
        git_semver.update_changelog("NONEXISTENT.md", "0.1.0")
        captured = capsys.readouterr()
        assert "not found, skipping changelog" in captured.out

    def test_subdir_changelog(self, tmp_repo):
        (tmp_repo / "frontend").mkdir()
        (tmp_repo / "frontend" / "CHANGELOG.md").write_text("# Changelog\n")
        with patch.object(git_semver, "get_commits_since_tag", return_value=["fix: bug"]):
            git_semver.update_changelog(
                "frontend/CHANGELOG.md", "1.0.1", subdir="frontend",
            )
        content = (tmp_repo / "frontend" / "CHANGELOG.md").read_text()
        assert "## [1.0.1]" in content

    def test_no_commits_shows_no_notable(self, tmp_repo):
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")
        with patch.object(git_semver, "get_commits_since_tag", return_value=[]):
            git_semver.update_changelog("CHANGELOG.md", "0.1.0")
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "No notable changes" in content
