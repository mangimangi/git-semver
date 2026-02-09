"""Tests for git helper functions and tag formatting."""

from unittest.mock import MagicMock, patch

import pytest

import git_semver


class TestGit:
    def test_successful_command(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "output"
        result.stderr = ""
        with patch("subprocess.run", return_value=result) as mock_run:
            r = git_semver.git("status")
            assert r.stdout == "output"
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == ["git", "status"]

    def test_failed_command_raises(self):
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        result.stderr = "fatal: error"
        with patch("subprocess.run", return_value=result):
            with pytest.raises(git_semver.SemverError, match="git status failed"):
                git_semver.git("status")

    def test_failed_command_check_false(self):
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        result.stderr = "not found"
        with patch("subprocess.run", return_value=result):
            r = git_semver.git("describe", "--tags", check=False)
            assert r.returncode == 1

    def test_capture_false(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = None
        result.stderr = None
        with patch("subprocess.run", return_value=result) as mock_run:
            git_semver.git("push", capture=False)
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["capture_output"] is False

    def test_failed_no_capture_empty_stderr(self):
        result = MagicMock()
        result.returncode = 1
        result.stderr = None
        with patch("subprocess.run", return_value=result):
            with pytest.raises(git_semver.SemverError):
                git_semver.git("push", capture=False)


class TestGetChangedFiles:
    def test_normal_diff(self, mock_git):
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "file1.py\nfile2.js\n"
        mock.return_value = result

        files = git_semver.get_changed_files("abc123")
        assert files == ["file1.py", "file2.js"]

    def test_initial_commit(self, mock_git):
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "file1.py\n"
        mock.return_value = result

        files = git_semver.get_changed_files("0" * 40)
        # Should use diff-tree for initial commit
        assert calls[0][0][0] == "diff-tree"

    def test_empty_output(self, mock_git):
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = ""
        mock.return_value = result

        files = git_semver.get_changed_files("abc123")
        assert files == []


class TestGetCommitsSinceTag:
    def test_with_explicit_tag(self, mock_git):
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "feat: thing\nfix: bug\n"
        mock.return_value = result

        commits = git_semver.get_commits_since_tag(tag="v1.0.0")
        assert commits == ["feat: thing", "fix: bug"]

    def test_auto_detect_tag(self, mock_git):
        calls, mock = mock_git
        # First call: describe (finds tag)
        describe_result = MagicMock()
        describe_result.returncode = 0
        describe_result.stdout = "v1.0.0"
        # Second call: log
        log_result = MagicMock()
        log_result.stdout = "new commit\n"
        mock.side_effect = [describe_result, log_result]

        commits = git_semver.get_commits_since_tag()
        assert commits == ["new commit"]

    def test_no_existing_tags(self, mock_git):
        calls, mock = mock_git
        # describe fails (no tags)
        describe_result = MagicMock()
        describe_result.returncode = 128
        describe_result.stdout = ""
        # log returns all commits
        log_result = MagicMock()
        log_result.stdout = "first commit\nsecond commit\n"
        mock.side_effect = [describe_result, log_result]

        commits = git_semver.get_commits_since_tag()
        assert commits == ["first commit", "second commit"]

    def test_subdir_tag_pattern(self, mock_git):
        calls, mock = mock_git
        describe_result = MagicMock()
        describe_result.returncode = 0
        describe_result.stdout = "frontend/v1.0.0"
        log_result = MagicMock()
        log_result.stdout = "fix: frontend bug\n"
        mock.side_effect = [describe_result, log_result]

        commits = git_semver.get_commits_since_tag(subdir="frontend")
        # Verify describe used subdir pattern
        assert calls[0][0] == (
            "describe", "--tags", "--abbrev=0", "--match", "frontend/v*",
        )

    def test_empty_log(self, mock_git):
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = ""
        mock.return_value = result

        commits = git_semver.get_commits_since_tag(tag="v1.0.0")
        assert commits == []


class TestFormatTag:
    def test_root(self):
        assert git_semver.format_tag("1.2.3") == "v1.2.3"

    def test_subdir(self):
        assert git_semver.format_tag("1.2.3", subdir="frontend") == "frontend/v1.2.3"

    def test_nested_subdir(self):
        assert git_semver.format_tag("0.1.0", subdir="packages/core") == "packages/core/v0.1.0"

    def test_none_subdir(self):
        assert git_semver.format_tag("1.0.0", subdir=None) == "v1.0.0"
