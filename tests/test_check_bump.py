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
    for key in ("CICD_BASE", "CICD_HEAD", "CICD_SOURCE_BRANCH",
                "CICD_TARGET_BRANCH", "CICD_WRITE_TOKEN"):
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


def set_config(repo, **extra):
    cfg = {"version_file": "VERSION", "files": ["src/**"]}
    cfg.update(extra)
    write(repo, CONFIG, json.dumps(cfg))


@pytest.fixture
def pr_repo(repo):
    """`repo` with bump_on pull_request, an updates target and a changelog."""
    set_config(repo, bump_on="pull_request",
               updates={"pkg.py": ["__version__ = "]})
    write(repo, "pkg.py", '__version__ = "1.2.3"\n')
    write(repo, "CHANGELOG.md", "# Changelog\n\n## [1.2.3] - 2026-01-01\n")
    g(repo, "checkout", "-q", "main")
    commit(repo, "pull request mode")
    g(repo, "checkout", "-q", "pr")
    g(repo, "reset", "-q", "--hard", "main")
    return repo


def count(repo):
    return int(g(repo, "rev-list", "--count", "HEAD"))


class TestCheckBumpFix:
    def test_unbumped_change_gets_one_patch_commit(self, pr_repo, capsys):
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo, "feat: change app")
        before = count(pr_repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert count(pr_repo) == before + 1
        assert (pr_repo / "VERSION").read_text() == "1.2.4\n"
        assert '__version__ = "1.2.4"' in (pr_repo / "pkg.py").read_text()
        changelog = (pr_repo / "CHANGELOG.md").read_text()
        assert "## [1.2.4]" in changelog
        assert "feat: change app" in changelog
        assert g(pr_repo, "log", "-1", "--format=%s") == \
            "chore: bump version (root 1.2.3 -> 1.2.4)"
        assert sorted(g(pr_repo, "show", "--name-only", "--format=",
                        "HEAD").split()) == ["CHANGELOG.md", "VERSION", "pkg.py"]
        assert "Raised root: 1.2.3 -> 1.2.4" in out
        assert g(pr_repo, "rev-parse", "HEAD") in out
        assert "git-semver bump patch --no-push" in out
        assert g(pr_repo, "status", "--porcelain") == ""
        # The fixed head now passes the check.
        assert run_check(capsys, base="main")[0] == 0

    def test_root_and_subdir_one_commit(self, pr_repo, capsys):
        set_config(pr_repo, bump_on="pull_request",
                   backend={"version_file": "backend/VERSION",
                            "files": ["backend/**"]})
        write(pr_repo, "backend/VERSION", "0.3.0\n")
        write(pr_repo, "backend/CHANGELOG.md", "# Changelog\n")
        g(pr_repo, "checkout", "-q", "main")
        commit(pr_repo, "add backend")
        g(pr_repo, "checkout", "-q", "pr")
        g(pr_repo, "reset", "-q", "--hard", "main")
        write(pr_repo, "src/app.py", "b\n")
        write(pr_repo, "backend/x.py", "b\n")
        commit(pr_repo)
        before = count(pr_repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert count(pr_repo) == before + 1
        assert g(pr_repo, "log", "-1", "--format=%s") == (
            "chore: bump version (root 1.2.3 -> 1.2.4, backend 0.3.0 -> 0.3.1)")
        assert (pr_repo / "backend/VERSION").read_text() == "0.3.1\n"
        assert "## [0.3.1]" in (pr_repo / "backend/CHANGELOG.md").read_text()

    def test_only_unbumped_component_raised(self, pr_repo, capsys):
        set_config(pr_repo, bump_on="pull_request", changelog=False,
                   backend={"version_file": "backend/VERSION",
                            "files": ["backend/**"]})
        write(pr_repo, "backend/VERSION", "0.3.0\n")
        g(pr_repo, "checkout", "-q", "main")
        commit(pr_repo, "add backend")
        g(pr_repo, "checkout", "-q", "pr")
        g(pr_repo, "reset", "-q", "--hard", "main")
        write(pr_repo, "src/app.py", "b\n")
        write(pr_repo, "VERSION", "1.3.0\n")
        write(pr_repo, "backend/x.py", "b\n")
        commit(pr_repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert g(pr_repo, "log", "-1", "--format=%s") == \
            "chore: bump version (backend 0.3.0 -> 0.3.1)"
        assert (pr_repo / "VERSION").read_text() == "1.3.0\n"
        assert g(pr_repo, "show", "--name-only", "--format=", "HEAD") == \
            "backend/VERSION"

    @pytest.mark.parametrize("new", ["1.2.4", "1.3.0", "2.0.0"])
    def test_bump_already_made_no_commit(self, pr_repo, capsys, new):
        write(pr_repo, "src/app.py", "b\n")
        write(pr_repo, "VERSION", new + "\n")
        commit(pr_repo)
        before = count(pr_repo)
        rc, _ = run_check(capsys, base="main")
        assert rc == 0
        assert count(pr_repo) == before

    @pytest.mark.parametrize("version", ["1.2.2\n", "1.3\n", None])
    def test_down_malformed_missing_never_fixed(self, pr_repo, capsys, version):
        set_config(pr_repo, bump_on="pull_request",
                   backend={"version_file": "backend/VERSION",
                            "files": ["backend/**"]})
        write(pr_repo, "backend/VERSION", "0.3.0\n")
        g(pr_repo, "checkout", "-q", "main")
        commit(pr_repo, "add backend")
        g(pr_repo, "checkout", "-q", "pr")
        g(pr_repo, "reset", "-q", "--hard", "main")
        write(pr_repo, "src/app.py", "b\n")
        write(pr_repo, "backend/x.py", "b\n")  # fixable on its own
        if version is None:
            (pr_repo / "VERSION").unlink()
        else:
            write(pr_repo, "VERSION", version)
        commit(pr_repo)
        before = count(pr_repo)
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert count(pr_repo) == before
        assert "root: FAIL" in out
        assert "Not fixing: the version of root" in out
        assert g(pr_repo, "status", "--porcelain") == ""

    def test_nothing_changed_no_commit(self, pr_repo, capsys):
        write(pr_repo, "README.md", "x\n")
        commit(pr_repo)
        before = count(pr_repo)
        assert run_check(capsys, base="main")[0] == 0
        assert count(pr_repo) == before

    def test_no_fix_overrides_pull_request(self, pr_repo, capsys):
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        before = count(pr_repo)
        rc, out = run_check(capsys, base="main", fix=False)
        assert rc == 1
        assert count(pr_repo) == before
        assert "VERSION is still 1.2.3" in out
        assert "Raised" not in out

    def test_push_bump_false_checks_only(self, pr_repo, capsys):
        set_config(pr_repo, bump_on="pull_request", push_bump=False)
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        before = count(pr_repo)
        assert run_check(capsys, base="main")[0] == 1
        assert count(pr_repo) == before

    def test_merge_mode_default_checks_only(self, repo, capsys):
        set_config(repo, push_bump=True)
        write(repo, "src/app.py", "b\n")
        commit(repo)
        before = count(repo)
        assert run_check(capsys, base="main")[0] == 1
        assert count(repo) == before

    def test_fix_overrides_merge_mode(self, repo, capsys):
        write(repo, "src/app.py", "b\n")
        commit(repo)
        before = count(repo)
        rc, out = run_check(capsys, base="main", fix=True)
        assert rc == 1
        assert count(repo) == before + 1
        assert (repo / "VERSION").read_text() == "1.2.4\n"

    def test_head_not_checked_out_errors(self, pr_repo, capsys):
        write(pr_repo, "src/app.py", "b\n")
        bad = commit(pr_repo)
        write(pr_repo, "README.md", "later\n")
        commit(pr_repo)
        with pytest.raises(git_semver.SemverError,
                           match=f"head is {bad}, HEAD is "):
            git_semver.cmd_check_bump(args(base="main", head=bad))

    def test_unrelated_worktree_changes_not_committed(self, pr_repo, capsys):
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        write(pr_repo, "README.md", "dirty\n")
        write(pr_repo, "untracked.txt", "x\n")
        run_check(capsys, base="main")
        files = g(pr_repo, "show", "--name-only", "--format=", "HEAD").split()
        assert "README.md" not in files and "untracked.txt" not in files
        status = g(pr_repo, "status", "--porcelain")
        assert "README.md" in status and "untracked.txt" in status

    def test_tag_ahead_baseline_still_above_base(self, pr_repo, capsys):
        g(pr_repo, "tag", "v1.2.7")
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        run_check(capsys, base="main")
        assert (pr_repo / "VERSION").read_text() == "1.2.8\n"

    def test_configured_identity_is_used(self, pr_repo, capsys):
        g(pr_repo, "config", "user.name", "Someone")
        g(pr_repo, "config", "user.email", "someone@example.com")
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        run_check(capsys, base="main")
        assert g(pr_repo, "log", "-1", "--format=%ae") == "someone@example.com"

    def test_fallback_identity_without_config(self, pr_repo, capsys,
                                              monkeypatch):
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        run_check(capsys, base="main")
        assert g(pr_repo, "log", "-1", "--format=%ae") == \
            "git-semver@users.noreply.github.com"


FAKE_TOKEN = "ghp_FAKEfake0123456789abcdefABCDEF012345"
FAKE_BASIC = git_semver.token_header(FAKE_TOKEN).split(" ", 2)[2]


@pytest.fixture
def origin_pr(pr_repo, tmp_path_factory, monkeypatch):
    """pr_repo with an unbumped change on `pr`, pushed to a bare `origin`."""
    bare = tmp_path_factory.mktemp("origin") / "origin.git"
    g(pr_repo, "init", "-q", "--bare", str(bare))
    g(pr_repo, "remote", "add", "origin", str(bare))
    write(pr_repo, "src/app.py", "b\n")
    commit(pr_repo, "feat: change app")
    g(pr_repo, "push", "-q", "origin", "main", "pr")
    monkeypatch.setenv("CICD_WRITE_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("CICD_SOURCE_BRANCH", "pr")
    monkeypatch.setenv("CICD_TARGET_BRANCH", "main")
    return pr_repo


@pytest.fixture
def push_boundary(monkeypatch):
    """Run git for real except `git push`, which is recorded with its env."""
    calls = []
    real_git = git_semver.git
    response = {"rc": 0, "stderr": "", "stdout": ""}

    def _git(*a, check=True, capture=True, env=None):
        if a[:1] == ("push",):
            calls.append((a, env))
            return subprocess.CompletedProcess(
                ["git", *a], response["rc"], response["stdout"],
                response["stderr"])
        return real_git(*a, check=check, capture=capture, env=env)

    monkeypatch.setattr(git_semver, "git", _git)
    return calls, response


def remote_sha(repo, branch):
    bare = g(repo, "remote", "get-url", "origin")
    return g(repo, "--git-dir", bare, "rev-parse", branch)


class TestCheckBumpPush:
    def test_pushes_to_source_branch(self, origin_pr, push_boundary, capsys):
        calls, _ = push_boundary
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        sha = g(origin_pr, "rev-parse", "HEAD")
        assert sha != remote_sha(origin_pr, "pr")
        assert len(calls) == 1
        argv, env = calls[0]
        assert argv == ("push", "origin", "HEAD:refs/heads/pr")
        assert FAKE_TOKEN not in " ".join(argv)
        assert env["GIT_CONFIG_COUNT"] == "2"
        assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
        assert env["GIT_CONFIG_VALUE_0"] == ""
        assert env["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraheader"
        assert env["GIT_CONFIG_VALUE_1"] == f"AUTHORIZATION: basic {FAKE_BASIC}"
        assert f"Pushed {sha} to pr" in out
        assert f"The pushed commit {sha} starts its own run; wait for that one" in out

    def test_bump_already_made_no_commit_no_push(self, origin_pr, push_boundary,
                                                 capsys):
        calls, _ = push_boundary
        write(origin_pr, "VERSION", "1.3.0\n")
        commit(origin_pr)
        assert run_check(capsys, base="main")[0] == 0
        assert calls == []

    def _refused(self, capsys, push_boundary, reason, pushes=0, **kwargs):
        calls, _ = push_boundary
        rc, out = run_check(capsys, base="main", **kwargs)
        assert rc == 1
        assert len(calls) == pushes
        assert f"Not pushing the bump: {reason}" in out
        assert "  fix: run `git-semver bump patch --no-push` on the branch" in out
        return out

    def test_no_token(self, origin_pr, push_boundary, capsys, monkeypatch):
        monkeypatch.delenv("CICD_WRITE_TOKEN")
        self._refused(capsys, push_boundary,
                      "no CICD_WRITE_TOKEN: declare it on the version check job")

    def test_empty_token(self, origin_pr, push_boundary, capsys, monkeypatch):
        monkeypatch.setenv("CICD_WRITE_TOKEN", "")
        self._refused(capsys, push_boundary, "no CICD_WRITE_TOKEN")

    def test_no_source_branch(self, origin_pr, push_boundary, capsys,
                              monkeypatch):
        monkeypatch.delenv("CICD_SOURCE_BRANCH")
        self._refused(capsys, push_boundary, "source branch unknown")

    def test_source_is_target(self, origin_pr, push_boundary, capsys,
                              monkeypatch):
        monkeypatch.setenv("CICD_TARGET_BRANCH", "pr")
        self._refused(capsys, push_boundary,
                      "source branch pr is the target branch")

    @pytest.mark.parametrize("branch", ["main", "master"])
    def test_source_is_release_branch(self, origin_pr, push_boundary, capsys,
                                      monkeypatch, branch):
        monkeypatch.setenv("CICD_SOURCE_BRANCH", branch)
        monkeypatch.setenv("CICD_TARGET_BRANCH", "plan/x")
        self._refused(capsys, push_boundary,
                      f"source branch {branch} is a release branch")

    def test_branch_not_on_origin(self, origin_pr, push_boundary, capsys,
                                  monkeypatch):
        monkeypatch.setenv("CICD_SOURCE_BRANCH", "from-a-fork")
        self._refused(capsys, push_boundary,
                      "branch from-a-fork is not on origin")

    def test_branch_moved_on(self, origin_pr, push_boundary, capsys):
        head = g(origin_pr, "rev-parse", "HEAD")
        g(origin_pr, "checkout", "-q", "-b", "later")
        write(origin_pr, "README.md", "later\n")
        later = commit(origin_pr)
        g(origin_pr, "push", "-q", "origin", "later:pr")
        g(origin_pr, "checkout", "-q", "pr")
        self._refused(capsys, push_boundary,
                      f"branch pr moved on from {head} (now {later})")

    def test_origin_unreadable(self, origin_pr, push_boundary, capsys):
        g(origin_pr, "remote", "remove", "origin")
        self._refused(capsys, push_boundary, "cannot read origin: ")

    def test_push_fails_redacted(self, origin_pr, push_boundary, capsys):
        _, response = push_boundary
        response["rc"] = 1
        response["stderr"] = (f"remote: denied for {FAKE_TOKEN}\n"
                              f"header basic {FAKE_BASIC}\n")
        out = self._refused(capsys, push_boundary,
                            "git push failed: remote: denied for ***",
                            pushes=1)
        assert FAKE_TOKEN not in out and FAKE_BASIC not in out
        assert "header basic ***" in out

    def test_push_fails_stdout_only(self, origin_pr, push_boundary, capsys):
        _, response = push_boundary
        response["rc"] = 1
        response["stdout"] = "rejected"
        self._refused(capsys, push_boundary, "git push failed: rejected",
                      pushes=1)

    def test_subdir_fix_line(self, origin_pr, push_boundary, capsys,
                             monkeypatch):
        set_config(origin_pr, bump_on="pull_request",
                   backend={"version_file": "backend/VERSION",
                            "files": ["backend/**"]})
        write(origin_pr, "VERSION", "1.3.0\n")
        write(origin_pr, "backend/VERSION", "0.1.0\n")
        g(origin_pr, "checkout", "-q", "main")
        commit(origin_pr, "backend")
        g(origin_pr, "checkout", "-q", "pr")
        g(origin_pr, "reset", "-q", "--hard", "main")
        write(origin_pr, "backend/x.py", "b\n")
        commit(origin_pr)
        monkeypatch.delenv("CICD_WRITE_TOKEN")
        rc, out = run_check(capsys, base="main")
        assert rc == 1
        assert "  fix: run `git-semver bump patch --no-push --subdir backend`" \
            " on the branch and push the commit" in out

    def test_args_override_env(self, origin_pr, push_boundary, capsys,
                               monkeypatch):
        calls, _ = push_boundary
        monkeypatch.setenv("CICD_SOURCE_BRANCH", "main")
        monkeypatch.setenv("CICD_TARGET_BRANCH", "pr")
        rc, out = run_check(capsys, base="main", source_branch="pr",
                            target_branch="main")
        assert rc == 1
        assert [c[0] for c in calls] == [("push", "origin", "HEAD:refs/heads/pr")]

    def test_no_fix_pushes_nothing(self, origin_pr, push_boundary, capsys):
        calls, _ = push_boundary
        before = count(origin_pr)
        rc, out = run_check(capsys, base="main", fix=False)
        assert rc == 1
        assert calls == [] and count(origin_pr) == before
        assert "git-semver bump patch --no-push" in out

    def test_real_push_leaks_no_token(self, origin_pr, capsys):
        rc = git_semver.cmd_check_bump(args(base="main"))
        captured = capsys.readouterr()
        assert rc == 1
        sha = g(origin_pr, "rev-parse", "HEAD")
        assert remote_sha(origin_pr, "pr") == sha
        assert f"Pushed {sha} to pr" in captured.out
        text = captured.out + captured.err
        text += g(origin_pr, "log", "-1", "--format=%B")
        text += g(origin_pr, "config", "--list", "--show-origin")
        text += (origin_pr / ".git" / "config").read_text()
        for secret in (FAKE_TOKEN, FAKE_BASIC):
            assert secret not in text
        assert "extraheader" not in text


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

    def test_fixing_mode_commits(self, pr_repo):
        write(pr_repo, "src/app.py", "b\n")
        commit(pr_repo)
        result = self._run(pr_repo, "--base", "main", "--fix")
        assert result.returncode == 1, result.stderr
        assert "Raised root: 1.2.3 -> 1.2.4" in result.stdout
        assert g(pr_repo, "log", "-1", "--format=%s") == \
            "chore: bump version (root 1.2.3 -> 1.2.4)"

    def test_fixing_mode_pushes(self, origin_pr):
        result = self._run(origin_pr, "--base", "main", "--source-branch", "pr",
                           "--target-branch", "main",
                           env_extra={"CICD_WRITE_TOKEN": FAKE_TOKEN})
        assert result.returncode == 1, result.stderr
        sha = g(origin_pr, "rev-parse", "HEAD")
        assert remote_sha(origin_pr, "pr") == sha
        assert "starts its own run; wait for that one" in result.stdout
        assert FAKE_TOKEN not in result.stdout + result.stderr

    def test_fix_and_no_fix_exclusive(self, repo):
        result = self._run(repo, "--base", "main", "--fix", "--no-fix")
        assert result.returncode == 2
        assert "not allowed with" in result.stderr

    def test_no_base_exits_1_on_stderr(self, repo):
        result = self._run(repo)
        assert result.returncode == 1
        assert result.stderr.startswith("Error: no base")
