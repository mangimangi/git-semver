"""Tests for `git-semver check-bump`, against real temporary git repositories.

Local git only: no token, no network.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import git_semver

ROOT = Path(__file__).parent.parent
GIT_SEMVER = str(ROOT / "git-semver")
CONFIG = ".vendored/configs/git-semver.json"


def g(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def write(repo, path, content):
    p = Path(repo) / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def commit(repo, message="change"):
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "--allow-empty", "-m", message)
    return g(repo, "rev-parse", "HEAD")


def args(**kwargs):
    defaults = {"config": None, "base": None, "head": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo on `main` with root files ["src/**"] at 1.2.3, and a branch `pr`."""
    for key in ("CICD_BASE", "CICD_HEAD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    g(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, CONFIG, json.dumps({
        "version_file": "VERSION", "files": ["src/**"],
    }))
    write(tmp_path, "VERSION", "1.2.3\n")
    write(tmp_path, "src/app.py", "a\n")
    write(tmp_path, "README.md", "readme\n")
    commit(tmp_path, "initial")
    g(tmp_path, "checkout", "-q", "-b", "pr")
    return tmp_path


def run_check(capsys, **kwargs):
    rc = git_semver.cmd_check_bump(args(**kwargs))
    return rc, capsys.readouterr().out


class TestCheckBumpRoot:
    def test_no_configured_file_changed_passes(self, repo, capsys):
        write(repo, "README.md", "changed\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert "root: no configured file changed" in out

    def test_unchanged_version_fails_with_fix(self, repo, capsys):
        write(repo, "src/app.py", "b\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "root: FAIL" in out
        assert "src/app.py" in out
        assert "VERSION is still 1.2.3" in out
        assert "base main has 1.2.3" in out
        assert "`git-semver bump patch --no-push`" in out
        assert "--subdir" not in out

    def test_lower_version_fails(self, repo, capsys):
        write(repo, "src/app.py", "b\n")
        write(repo, "VERSION", "1.2.2\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "went down to 1.2.2" in out
        assert "base main has 1.2.3" in out
        assert "git-semver bump patch --no-push" in out

    def test_malformed_version_fails(self, repo, capsys):
        write(repo, "src/app.py", "b\n")
        write(repo, "VERSION", "1.3\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "'1.3', not a valid X.Y.Z version" in out
        assert "git-semver bump patch --no-push" in out

    def test_missing_version_file_fails(self, repo, capsys):
        write(repo, "src/app.py", "b\n")
        (repo / "VERSION").unlink()
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "VERSION is missing" in out

    @pytest.mark.parametrize("new", ["1.2.4", "1.3.0", "2.0.0"])
    def test_any_increase_passes(self, repo, capsys, new):
        write(repo, "src/app.py", "b\n")
        write(repo, "VERSION", new + "\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert f"root: version raised 1.2.3 -> {new}" in out

    def test_version_file_alone_up_passes(self, repo, capsys):
        write(repo, "VERSION", "1.2.4\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert "version raised 1.2.3 -> 1.2.4" in out

    def test_version_file_alone_down_fails(self, repo, capsys):
        write(repo, "VERSION", "1.0.0\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "VERSION changed" in out
        assert "went down to 1.0.0" in out

    def test_version_file_alone_malformed_fails(self, repo, capsys):
        write(repo, "VERSION", "banana\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "not a valid X.Y.Z version" in out

    def test_no_version_at_base_any_valid_head_passes(self, tmp_path,
                                                      monkeypatch, capsys):
        for key in ("CICD_BASE", "CICD_HEAD"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.chdir(tmp_path)
        g(tmp_path, "init", "-q", "-b", "main")
        write(tmp_path, CONFIG, json.dumps({"files": ["src/**"]}))
        commit(tmp_path, "initial")
        g(tmp_path, "checkout", "-q", "-b", "pr")
        write(tmp_path, "src/app.py", "a\n")
        write(tmp_path, "VERSION", "0.1.0\n")
        commit(tmp_path)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert "version raised none -> 0.1.0" in out

    def test_only_branch_changes_count(self, repo, capsys):
        """Three-dot: a change on the base since the branch left is ignored."""
        g(repo, "checkout", "-q", "main")
        write(repo, "src/app.py", "on main\n")
        commit(repo)
        g(repo, "checkout", "-q", "pr")
        write(repo, "README.md", "pr\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert "root: no configured file changed" in out

    def test_no_files_configured_is_skipped(self, repo, capsys):
        write(repo, CONFIG, json.dumps({"files": []}))
        write(repo, "src/app.py", "b\n")
        commit(repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert "root: skipped (no 'files' configured)" in out


class TestCheckBumpSubdir:
    @pytest.fixture
    def mono(self, repo):
        write(repo, CONFIG, json.dumps({
            "version_file": "VERSION", "files": ["src/**"],
            "backend": {"version_file": "backend/VERSION",
                        "files": ["backend/**"]},
        }))
        write(repo, "backend/VERSION", "0.4.0\n")
        write(repo, "backend/main.py", "a\n")
        g(repo, "checkout", "-q", "main")
        commit(repo, "add backend")
        g(repo, "checkout", "-q", "pr")
        g(repo, "reset", "-q", "--hard", "main")
        return repo

    def test_subdir_unbumped_fails_with_subdir_fix(self, mono, capsys):
        write(mono, "backend/main.py", "b\n")
        commit(mono)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "root: no configured file changed" in out
        assert "backend: FAIL" in out
        assert "backend/VERSION is still 0.4.0" in out
        assert "`git-semver bump patch --no-push --subdir backend`" in out

    def test_subdir_bumped_passes(self, mono, capsys):
        write(mono, "backend/main.py", "b\n")
        write(mono, "backend/VERSION", "0.5.0\n")
        commit(mono)
        rc, out = run_check(capsys, base="main")
        assert rc == 0
        assert "backend: version raised 0.4.0 -> 0.5.0" in out

    def test_one_failing_component_fails_the_run(self, mono, capsys):
        write(mono, "backend/main.py", "b\n")
        write(mono, "backend/VERSION", "0.5.0\n")
        write(mono, "src/app.py", "b\n")
        commit(mono)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "root: FAIL" in out
        assert "backend: version raised" in out


class TestCheckBumpInputs:
    def test_env_vars_used_without_args(self, repo, capsys, monkeypatch):
        base = g(repo, "rev-parse", "main")
        write(repo, "src/app.py", "b\n")
        bad = commit(repo)
        write(repo, "VERSION", "1.2.4\n")
        commit(repo)
        monkeypatch.setenv("CICD_BASE", base)
        monkeypatch.setenv("CICD_HEAD", bad)
        rc, out = run_check(capsys)
        assert rc == 1
        assert "VERSION is still 1.2.3" in out

    def test_head_defaults_to_HEAD(self, repo, capsys, monkeypatch):
        write(repo, "src/app.py", "b\n")
        write(repo, "VERSION", "1.2.4\n")
        commit(repo)
        monkeypatch.setenv("CICD_BASE", "main")
        rc, out = run_check(capsys)
        assert rc == 0

    def test_args_override_env(self, repo, capsys, monkeypatch):
        write(repo, "src/app.py", "b\n")
        bad = commit(repo)
        write(repo, "VERSION", "1.2.4\n")
        good = commit(repo)
        monkeypatch.setenv("CICD_BASE", "does-not-exist")
        monkeypatch.setenv("CICD_HEAD", bad)
        rc, out = run_check(capsys, base="main", head=good)
        assert rc == 0

    def test_missing_base_errors_naming_both(self, repo):
        with pytest.raises(git_semver.SemverError,
                           match=r"--base <rev> or set CICD_BASE"):
            git_semver.cmd_check_bump(args())

    def test_unknown_base_errors(self, repo):
        with pytest.raises(git_semver.SemverError, match="not a commit: nope"):
            git_semver.cmd_check_bump(args(base="nope"))

    def test_writes_nothing(self, repo, capsys):
        write(repo, "src/app.py", "b\n")
        commit(repo)
        before_head = g(repo, "rev-parse", "HEAD")
        assert run_check(capsys, base="main")[0] == 1
        assert g(repo, "status", "--porcelain") == ""
        assert g(repo, "tag", "-l") == ""
        assert g(repo, "rev-parse", "HEAD") == before_head


class TestCheckBumpProcess:
    """Run as CI does, through the script's entry point."""

    def _run(self, repo, *extra, env_extra=None):
        import os
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("CICD_", "GITHUB_", "INPUT_"))}
        env.update(env_extra or {})
        return subprocess.run([sys.executable, GIT_SEMVER, "check-bump", *extra],
                              cwd=repo, env=env, capture_output=True,
                              text=True, check=False)

    def test_fails_with_exit_1(self, repo):
        write(repo, "src/app.py", "b\n")
        commit(repo)
        result = self._run(repo, env_extra={"CICD_BASE": "main"})
        assert result.returncode == 1
        assert "git-semver bump patch --no-push" in result.stdout

    def test_passes_with_exit_0(self, repo):
        write(repo, "src/app.py", "b\n")
        write(repo, "VERSION", "1.2.4\n")
        commit(repo)
        result = self._run(repo, "--base", "main", "--head", "HEAD")
        assert result.returncode == 0, result.stderr

    def test_no_base_exits_1_on_stderr(self, repo):
        result = self._run(repo)
        assert result.returncode == 1
        assert result.stderr.startswith("Error: no base")
