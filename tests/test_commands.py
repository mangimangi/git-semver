"""Tests for CLI commands (version, check, bump, bump-all)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import git_semver


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_args(**kwargs):
    """Create a SimpleNamespace mimicking parsed args."""
    defaults = {
        "config": None,
        "subdir": None,
        "since": None,
        "bump_type": "patch",
        "description": None,
        "no_push": False,
        "no_commit": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── cmd_version ─────────────────────────────────────────────────────────────

class TestCmdVersion:
    def test_prints_root_version(self, make_config, make_version_file, capsys):
        path = make_config({"files": [], "updates": {}})
        make_version_file("1.2.3")
        git_semver.cmd_version(make_args(config=path))
        assert capsys.readouterr().out.strip() == "1.2.3"

    def test_prints_subdir_version(self, make_config, make_version_file, capsys):
        path = make_config({
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": [], "updates": {},
            },
        })
        make_version_file("2.0.0", path="frontend/VERSION")
        git_semver.cmd_version(make_args(config=path, subdir="frontend"))
        assert capsys.readouterr().out.strip() == "2.0.0"

    def test_nonexistent_subdir(self, make_config, make_version_file):
        path = make_config({"files": [], "updates": {}})
        make_version_file("1.0.0")
        with pytest.raises(git_semver.SemverError, match="Subdirectory 'nope' not found"):
            git_semver.cmd_version(make_args(config=path, subdir="nope"))


# ── cmd_check ───────────────────────────────────────────────────────────────

class TestCmdCheck:
    def test_matching_files_returns_0(self, make_config, mock_git, capsys):
        path = make_config({"files": ["src/**/*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "src/main.py\n"
        mock.return_value = result

        rc = git_semver.cmd_check(make_args(config=path, since="abc"))
        assert rc == 0
        assert "Matched" in capsys.readouterr().out

    def test_no_matching_files_returns_1(self, make_config, mock_git, capsys):
        path = make_config({"files": ["src/**/*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "README.md\n"
        mock.return_value = result

        rc = git_semver.cmd_check(make_args(config=path, since="abc"))
        assert rc == 1
        assert "No matching files" in capsys.readouterr().out

    def test_no_files_changed_returns_1(self, make_config, mock_git, capsys):
        path = make_config({"files": ["src/**/*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = ""
        mock.return_value = result

        rc = git_semver.cmd_check(make_args(config=path, since="abc"))
        assert rc == 1
        assert "No files changed" in capsys.readouterr().out

    def test_default_since(self, make_config, mock_git):
        """Without --since, defaults to HEAD~1."""
        path = make_config({"files": ["*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = ""
        mock.return_value = result

        git_semver.cmd_check(make_args(config=path))
        # Should have called git diff with HEAD~1
        assert calls[0][0] == ("diff", "--name-only", "HEAD~1", "HEAD")

    def test_with_subdir(self, make_config, mock_git, capsys):
        path = make_config({
            "frontend": {
                "files": ["frontend/**/*.js"],
                "updates": {},
            },
        })
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "frontend/app.js\n"
        mock.return_value = result

        rc = git_semver.cmd_check(make_args(config=path, subdir="frontend", since="abc"))
        assert rc == 0

    def test_empty_files_raises(self, make_config, mock_git):
        path = make_config({"files": [], "updates": {}})
        with pytest.raises(git_semver.SemverError, match="No 'files' patterns configured"):
            git_semver.cmd_check(make_args(config=path, since="abc"))


# ── cmd_bump ────────────────────────────────────────────────────────────────

class TestCmdBump:
    def test_patch_no_commit(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": ["*.py"], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("1.0.0")

        git_semver.cmd_bump(make_args(config=path, no_commit=True))
        assert "1.0.1" in capsys.readouterr().out
        # Version file should be updated
        from pathlib import Path
        assert Path("VERSION").read_text().strip() == "1.0.1"

    def test_minor_bump(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": [], "updates": {},
            "changelog": False,
        })
        make_version_file("1.2.3")

        git_semver.cmd_bump(make_args(config=path, bump_type="minor", no_commit=True))
        assert "1.3.0" in capsys.readouterr().out

    def test_major_bump(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": [], "updates": {},
            "changelog": False,
        })
        make_version_file("1.2.3")

        git_semver.cmd_bump(make_args(config=path, bump_type="major", no_commit=True))
        assert "2.0.0" in capsys.readouterr().out

    def test_bump_with_commit_and_tag(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": [], "updates": {},
            "changelog": False,
        })
        make_version_file("1.0.0")

        git_semver.cmd_bump(make_args(config=path, no_push=True))
        out = capsys.readouterr().out
        assert "Committed: chore: bump version to v1.0.1" in out
        assert "Tagged: v1.0.1 + latest" in out
        calls, _ = mock_git
        # Verify git operations: add, commit, tag, tag -f
        git_cmds = [c[0] for c in calls]
        assert ("add", "-A") in git_cmds
        assert ("commit", "-m", "chore: bump version to v1.0.1") in git_cmds
        assert ("tag", "-a", "v1.0.1", "-m", "v1.0.1") in git_cmds
        assert ("tag", "-f", "latest") in git_cmds

    def test_bump_with_push(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": [], "updates": {},
            "changelog": False,
        })
        make_version_file("1.0.0")

        git_semver.cmd_bump(make_args(config=path))
        out = capsys.readouterr().out
        assert "pushed" in out
        calls, _ = mock_git
        git_cmds = [c[0] for c in calls]
        assert ("push",) in git_cmds

    def test_bump_subdir(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
            "changelog": False,
        })
        make_version_file("2.0.0", path="frontend/VERSION")

        git_semver.cmd_bump(make_args(config=path, subdir="frontend", no_commit=True))
        out = capsys.readouterr().out
        assert "frontend" in out
        assert "2.0.1" in out

    def test_bump_subdir_tag_format(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": [], "updates": {},
            },
            "changelog": False,
        })
        make_version_file("1.0.0", path="frontend/VERSION")

        git_semver.cmd_bump(make_args(config=path, subdir="frontend", no_push=True))
        calls, _ = mock_git
        git_cmds = [c[0] for c in calls]
        assert ("tag", "-a", "frontend/v1.0.1", "-m", "frontend/v1.0.1") in git_cmds
        assert ("commit", "-m", "chore: bump version to frontend/v1.0.1") in git_cmds

    def test_bump_with_description(self, make_config, make_version_file, mock_git, tmp_repo):
        path = make_config({
            "files": [], "updates": {},
            "changelog": {"file": "CHANGELOG.md"},
        })
        make_version_file("1.0.0")
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")

        git_semver.cmd_bump(make_args(
            config=path, no_commit=True, description="Major redesign",
        ))
        content = (tmp_repo / "CHANGELOG.md").read_text()
        assert "Major redesign" in content


# ── cmd_bump_all ────────────────────────────────────────────────────────────

class TestCmdBumpAll:
    def test_no_files_changed(self, make_config, mock_git, capsys):
        path = make_config({"files": ["*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = ""
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc"))
        assert "No files changed" in capsys.readouterr().out

    def test_no_components_triggered(self, make_config, mock_git, capsys):
        path = make_config({"files": ["src/**/*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "README.md\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc"))
        assert "No components triggered" in capsys.readouterr().out

    def test_bumps_root(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": ["*.py"], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("1.0.0")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "main.py\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc", no_push=True))
        out = capsys.readouterr().out
        assert "Root matched" in out
        assert "v1.0.1" in out

    def test_bumps_subdirectory(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
            "changelog": False,
        })
        make_version_file("2.0.0", path="frontend/VERSION")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "frontend/app.js\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc", no_commit=True))
        out = capsys.readouterr().out
        assert "frontend matched" in out
        assert "2.0.1" in out

    def test_bumps_root_and_subdir(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "version_file": "VERSION",
            "files": ["core/**/*.py"],
            "updates": {"VERSION": "file"},
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
            "changelog": False,
        })
        make_version_file("1.0.0")
        make_version_file("2.0.0", path="frontend/VERSION")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "core/lib.py\nfrontend/app.js\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc", no_push=True))
        out = capsys.readouterr().out
        assert "Root matched" in out
        assert "frontend matched" in out
        # Both should be committed in a single commit
        assert "chore: bump version v1.0.1, frontend/v2.0.1" in out

    def test_bump_all_no_commit(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": ["*.py"], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("1.0.0")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "main.py\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc", no_commit=True))
        out = capsys.readouterr().out
        assert "files only, no commit" in out
        # No git commit calls
        git_cmds = [c[0] for c in calls]
        assert not any("commit" in str(c) for c in git_cmds)

    def test_bump_all_no_push(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": ["*.py"], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("1.0.0")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "main.py\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc", no_push=True))
        out = capsys.readouterr().out
        assert "no push" in out

    def test_bump_all_with_push(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": ["*.py"], "updates": {},
            "changelog": False,
        })
        make_version_file("1.0.0")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "main.py\n"
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc"))
        out = capsys.readouterr().out
        assert "pushed" in out

    def test_missing_since_raises(self, make_config):
        path = make_config({"files": ["*.py"], "updates": {}})
        with pytest.raises(git_semver.SemverError, match="--since is required"):
            git_semver.cmd_bump_all(make_args(config=path, since=None))

    def test_only_matching_subdirs_bumped(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": ["frontend/**/*.js"],
                "updates": {},
            },
            "backend": {
                "version_file": "backend/VERSION",
                "files": ["backend/**/*.py"],
                "updates": {},
            },
            "changelog": False,
        })
        make_version_file("1.0.0", path="frontend/VERSION")
        make_version_file("3.0.0", path="backend/VERSION")
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = "frontend/app.js\n"  # Only frontend changed
        mock.return_value = result

        git_semver.cmd_bump_all(make_args(config=path, since="abc", no_commit=True))
        out = capsys.readouterr().out
        assert "frontend matched" in out
        assert "backend" not in out.lower().replace("changelog", "")
        # Only frontend version bumped
        from pathlib import Path
        assert Path("frontend/VERSION").read_text().strip() == "1.0.1"
        assert Path("backend/VERSION").read_text().strip() == "3.0.0"


# ── bump_component ──────────────────────────────────────────────────────────

class TestBumpComponent:
    def test_root_bump(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "files": [], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("1.0.0")

        subdir, old, new, tag = git_semver.bump_component(
            git_semver.load_config(path), bump_type="patch",
        )
        assert subdir is None
        assert old == "1.0.0"
        assert new == "1.0.1"
        assert tag == "v1.0.1"

    def test_subdir_bump(self, make_config, make_version_file, mock_git, capsys):
        path = make_config({
            "frontend": {
                "version_file": "frontend/VERSION",
                "files": [], "updates": {},
            },
            "changelog": False,
        })
        make_version_file("2.0.0", path="frontend/VERSION")

        config = git_semver.load_config(path)
        subdir, old, new, tag = git_semver.bump_component(
            config, subdir="frontend", bump_type="minor",
        )
        assert subdir == "frontend"
        assert old == "2.0.0"
        assert new == "2.1.0"
        assert tag == "frontend/v2.1.0"

    def test_tag_ahead_of_version_file(self, make_config, make_version_file, mock_git, capsys):
        """When a tag exists ahead of VERSION (e.g. queued CI run), use tag as baseline."""
        path = make_config({
            "files": [], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("0.2.25")

        # Mock git to return existing tag v0.2.26 from tag -l
        calls, mock = mock_git
        tag_result = MagicMock()
        tag_result.returncode = 0
        tag_result.stdout = "v0.2.25\nv0.2.26\n"

        def side_effect(*args, **kwargs):
            if args and args[0] == "tag" and args[1] == "-l":
                return tag_result
            r = MagicMock()
            r.stdout = ""
            r.returncode = 0
            return r

        mock.side_effect = side_effect

        subdir, old, new, tag = git_semver.bump_component(
            git_semver.load_config(path), bump_type="patch",
        )
        assert new == "0.2.27"
        assert tag == "v0.2.27"
        out = capsys.readouterr().out
        assert "using as baseline" in out

    def test_tag_at_version_file_no_adjustment(self, make_config, make_version_file, mock_git, capsys):
        """When the latest tag matches VERSION, no adjustment needed (normal state)."""
        path = make_config({
            "files": [], "updates": {"VERSION": "file"},
            "changelog": False,
        })
        make_version_file("1.0.0")

        calls, mock = mock_git
        tag_result = MagicMock()
        tag_result.returncode = 0
        tag_result.stdout = "v1.0.0\n"

        def side_effect(*args, **kwargs):
            if args and args[0] == "tag" and args[1] == "-l":
                return tag_result
            r = MagicMock()
            r.stdout = ""
            r.returncode = 0
            return r

        mock.side_effect = side_effect

        subdir, old, new, tag = git_semver.bump_component(
            git_semver.load_config(path), bump_type="patch",
        )
        # Normal bump, no tag adjustment
        assert new == "1.0.1"
        assert tag == "v1.0.1"
        out = capsys.readouterr().out
        assert "using as baseline" not in out


# ── CLI / main ──────────────────────────────────────────────────────────────

class TestMain:
    def test_no_command_exits(self):
        with patch("sys.argv", ["git-semver"]):
            with pytest.raises(SystemExit) as exc_info:
                git_semver.main()
            assert exc_info.value.code == 1

    def test_semver_error_exits_1(self, make_config):
        """SemverError is caught and exits with code 1."""
        path = make_config({"files": [], "updates": {}})
        # version command with missing version file -> SemverError
        with patch("sys.argv", ["git-semver", "--config", path, "version"]):
            with pytest.raises(SystemExit) as exc_info:
                git_semver.main()
            assert exc_info.value.code == 1

    def test_check_exit_code_propagated(self, make_config, mock_git):
        path = make_config({"files": ["*.py"], "updates": {}})
        calls, mock = mock_git
        result = MagicMock()
        result.stdout = ""
        mock.return_value = result

        with patch("sys.argv", ["git-semver", "--config", path, "check", "--since", "abc"]):
            with pytest.raises(SystemExit) as exc_info:
                git_semver.main()
            assert exc_info.value.code == 1

    def test_build_parser(self):
        parser = git_semver.build_parser()
        # Verify subcommands exist
        args = parser.parse_args(["version"])
        assert args.command == "version"

        args = parser.parse_args(["check", "--since", "abc"])
        assert args.command == "check"
        assert args.since == "abc"

        args = parser.parse_args(["bump", "minor", "--no-push"])
        assert args.command == "bump"
        assert args.bump_type == "minor"
        assert args.no_push is True

        args = parser.parse_args(["bump-all", "--since", "abc", "major"])
        assert args.command == "bump-all"
        assert args.since == "abc"
        assert args.bump_type == "major"

    def test_build_parser_subdir_flag(self):
        parser = git_semver.build_parser()
        args = parser.parse_args(["version", "--subdir", "frontend"])
        assert args.subdir == "frontend"

        args = parser.parse_args(["check", "--subdir", "backend", "--since", "abc"])
        assert args.subdir == "backend"

        args = parser.parse_args(["bump", "--subdir", "api"])
        assert args.subdir == "api"
