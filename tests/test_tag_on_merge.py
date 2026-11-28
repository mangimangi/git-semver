"""Tests for release's `"bump_on": "pull_request"` mode: tag the landed commit.

Real temporary git repositories, so tags really exist; `git push` and `gh`
are replaced at release's `run` boundary (recorded, never executed). No
network.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import semver_script as bar

ROOT = Path(__file__).parent.parent
RELEASE = str(ROOT / "release")
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


def tags_at(repo, rev="HEAD"):
    return sorted(t for t in g(repo, "tag", "--points-at", rev).split("\n") if t)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo in bump_on: pull_request mode at 1.0.0, tagged v1.0.0."""
    for key in [k for k in os.environ if k.startswith(("CICD_", "GITHUB_", "INPUT_"))]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bar, "SEMVER_CONFIG_PATH", CONFIG)
    g(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, CONFIG, json.dumps({
        "version_file": "VERSION", "files": ["src/**"],
        "bump_on": "pull_request",
    }))
    write(tmp_path, "VERSION", "1.0.0\n")
    write(tmp_path, "src/app.py", "a\n")
    commit(tmp_path, "initial")
    g(tmp_path, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    return tmp_path


@pytest.fixture
def boundary(monkeypatch):
    """Run every command for real except `git push` and `gh`, which are recorded."""
    calls = []
    real_run = bar.run

    def _run(*cmd, check=True, capture=True):
        calls.append(cmd)
        if cmd[0] == "gh" or cmd[:2] == ("git", "push"):
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(*cmd, check=check, capture=capture)

    monkeypatch.setattr(bar, "run", _run)
    return calls


def pushes(calls):
    return [c for c in calls if c[:2] == ("git", "push")]


def gh_calls(calls):
    return [c for c in calls if c[0] == "gh"]


def merge(repo, monkeypatch, version=None, files=None):
    """Land a change on main and point the merge env vars at it."""
    base = g(repo, "rev-parse", "HEAD")
    for path, content in (files or {"src/app.py": "changed\n"}).items():
        write(repo, path, content)
    if version:
        write(repo, "VERSION", version + "\n")
    landed = commit(repo, "feat: a change")
    monkeypatch.setenv("CICD_TRIGGER", "merge")
    monkeypatch.setenv("CICD_BASE", base)
    monkeypatch.setenv("CICD_HEAD", landed)
    return base, landed


class TestTagOnMerge:
    def test_untagged_version_tags_landed_commit(self, repo, boundary,
                                                 monkeypatch, capsys):
        _, landed = merge(repo, monkeypatch, version="1.1.0")
        bar.cmd_auto()
        assert tags_at(repo, landed) == ["v1.1.0"]
        assert pushes(boundary) == [("git", "push", "origin", "v1.1.0")]
        assert gh_calls(boundary) == [(
            "gh", "release", "create", "v1.1.0", "--repo", "owner/repo",
            "--title", "v1.1.0", "--generate-notes")]
        # No commit, no branch push, no latest.
        assert g(repo, "rev-parse", "HEAD") == landed
        assert g(repo, "tag", "-l", "latest") == ""
        assert not any("commit" in c for c in boundary)
        tag_type = g(repo, "cat-file", "-t", "v1.1.0")
        assert tag_type == "tag"  # annotated
        assert "Released v1.1.0" in capsys.readouterr().out

    def test_second_run_at_same_commit_does_nothing(self, repo, boundary,
                                                    monkeypatch, capsys):
        merge(repo, monkeypatch, version="1.1.0")
        bar.cmd_auto()
        boundary.clear()
        bar.cmd_auto()
        assert pushes(boundary) == []
        assert gh_calls(boundary) == []
        assert not any(c[:2] == ("git", "tag") for c in boundary)
        out = capsys.readouterr().out
        assert "v1.1.0 is already released" in out
        assert "Nothing to release" in out

    def test_tagged_at_ancestor_does_nothing(self, repo, boundary,
                                             monkeypatch, capsys):
        merge(repo, monkeypatch, files={"README.md": "docs\n"})
        bar.cmd_auto()
        assert pushes(boundary) == [] and gh_calls(boundary) == []
        assert "v1.0.0 is already released" in capsys.readouterr().out

    def test_tagged_elsewhere_version_unchanged_does_nothing(
            self, repo, boundary, monkeypatch, capsys):
        # v1.0.0 moves to a commit off main; main's VERSION stays 1.0.0.
        g(repo, "checkout", "-q", "-b", "side")
        side = commit(repo, "side")
        g(repo, "tag", "-f", "-a", "v1.0.0", "-m", "v1.0.0", side)
        g(repo, "checkout", "-q", "main")
        merge(repo, monkeypatch, files={"README.md": "docs\n"})
        bar.cmd_auto()
        assert pushes(boundary) == [] and gh_calls(boundary) == []
        assert "did not change VERSION; nothing to release" in \
            capsys.readouterr().out

    def test_tagged_elsewhere_version_changed_fails(self, repo, boundary,
                                                    monkeypatch, capsys):
        g(repo, "checkout", "-q", "-b", "other-pr")
        write(repo, "VERSION", "1.1.0\n")
        other = commit(repo, "other pr bumped too")
        g(repo, "tag", "-a", "v1.1.0", "-m", "v1.1.0", other)
        g(repo, "checkout", "-q", "main")
        _, landed = merge(repo, monkeypatch, version="1.1.0")
        with pytest.raises(SystemExit) as exc:
            bar.cmd_auto()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "VERSION to 1.1.0" in err
        assert f"v1.1.0 is already tagged at {other}" in err
        assert "git-semver bump patch --no-push" in err
        assert "Nothing was tagged or pushed." in err
        assert tags_at(repo, landed) == []
        assert pushes(boundary) == [] and gh_calls(boundary) == []

    def test_no_base_counts_as_version_changed(self, repo, boundary,
                                               monkeypatch, capsys):
        g(repo, "checkout", "-q", "-b", "side")
        side = commit(repo, "side")
        g(repo, "tag", "-f", "-a", "v1.0.0", "-m", "v1.0.0", side)
        g(repo, "checkout", "-q", "main")
        merge(repo, monkeypatch, files={"README.md": "docs\n"})
        monkeypatch.setenv("CICD_BASE", "0" * 40)
        with pytest.raises(SystemExit):
            bar.cmd_auto()
        assert "already tagged at" in capsys.readouterr().err

    def test_failure_in_one_component_creates_no_tag(self, repo, boundary,
                                                     monkeypatch, capsys):
        write(repo, CONFIG, json.dumps({
            "files": ["src/**"], "bump_on": "pull_request",
            "backend": {"version_file": "backend/VERSION", "files": ["backend/**"]},
        }))
        write(repo, "backend/VERSION", "not-a-version\n")
        _, landed = merge(repo, monkeypatch, version="1.1.0")
        with pytest.raises(SystemExit):
            bar.cmd_auto()
        assert "backend: backend/VERSION holds 'not-a-version'" in \
            capsys.readouterr().err
        assert tags_at(repo, landed) == []
        assert pushes(boundary) == []

    def test_subdirectory_tags_subdir_prefix(self, repo, boundary,
                                             monkeypatch, capsys):
        write(repo, CONFIG, json.dumps({
            "files": ["src/**"], "bump_on": "pull_request", "_vendor": {},
            "backend": {"version_file": "backend/VERSION",
                        "files": ["backend/**"]},
            "frontend": {"files": ["frontend/**"]},  # VERSION default
        }))
        _, landed = merge(repo, monkeypatch,
                          files={"backend/VERSION": "0.3.0\n"})
        bar.cmd_auto()
        # frontend reads the root VERSION by default -> frontend/v1.0.0 is new too.
        assert tags_at(repo, landed) == ["backend/v0.3.0", "frontend/v1.0.0"]
        assert sorted(pushes(boundary)) == [
            ("git", "push", "origin", "backend/v0.3.0"),
            ("git", "push", "origin", "frontend/v1.0.0"),
        ]
        assert len(gh_calls(boundary)) == 2

    def test_missing_root_version_file_is_skipped(self, repo, boundary,
                                                  monkeypatch, capsys):
        (repo / "VERSION").unlink()
        merge(repo, monkeypatch)
        bar.cmd_auto()
        out = capsys.readouterr().out
        assert "root: no VERSION at" in out
        assert "Nothing to release" in out

    def test_commit_subject_rules_not_consulted(self, repo, boundary,
                                                monkeypatch):
        base = g(repo, "rev-parse", "HEAD")
        write(repo, "VERSION", "1.0.1\n")
        landed = commit(repo, "chore: install something")
        monkeypatch.setenv("CICD_TRIGGER", "merge")
        monkeypatch.setenv("CICD_BASE", base)
        monkeypatch.setenv("CICD_HEAD", landed)
        bar.cmd_auto()
        assert tags_at(repo, landed) == ["v1.0.1"]

    def test_github_env_vars(self, repo, boundary, monkeypatch):
        base, landed = merge(repo, monkeypatch, version="2.0.0")
        for key in ("CICD_TRIGGER", "CICD_BASE", "CICD_HEAD"):
            monkeypatch.delenv(key)
        monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
        monkeypatch.setenv("GITHUB_EVENT_BEFORE", base)
        monkeypatch.setenv("GITHUB_SHA", landed)
        bar.cmd_auto()
        assert tags_at(repo, landed) == ["v2.0.0"]


class TestTagOnManual:
    def test_manual_releases_current_commit(self, repo, boundary,
                                            monkeypatch):
        write(repo, "VERSION", "1.2.0\n")
        head = commit(repo, "bump")
        monkeypatch.setenv("CICD_TRIGGER", "manual")
        bar.cmd_auto()
        assert tags_at(repo, head) == ["v1.2.0"]
        assert len(gh_calls(boundary)) == 1

    @pytest.mark.parametrize("name", [
        "CICD_INPUT_BUMP_TYPE", "INPUT_SUBDIRECTORY",
        "CICD_INPUT_CHANGELOG_DESCRIPTION"])
    def test_manual_with_bump_input_refused(self, repo, boundary,
                                            monkeypatch, capsys, name):
        monkeypatch.setenv("CICD_TRIGGER", "manual")
        monkeypatch.setenv(name, "minor")
        with pytest.raises(SystemExit) as exc:
            bar.cmd_auto()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "bumps the version in the pull request" in err
        assert "git-semver bump <patch|minor|major> --no-push" in err
        assert boundary == []

    def test_manual_with_empty_inputs_proceeds(self, repo, boundary,
                                               monkeypatch, capsys):
        monkeypatch.setenv("CICD_TRIGGER", "manual")
        monkeypatch.setenv("CICD_INPUT_BUMP_TYPE", "")
        bar.cmd_auto()
        assert "Nothing to release" in capsys.readouterr().out


class TestBumpOnSetting:
    def test_invalid_value_errors_naming_allowed(self, repo, monkeypatch,
                                                 capsys):
        write(repo, CONFIG, json.dumps({"bump_on": "push"}))
        monkeypatch.setenv("CICD_TRIGGER", "merge")
        with pytest.raises(SystemExit) as exc:
            bar.cmd_auto()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "bump_on is 'push'" in err
        assert '"merge", "pull_request"' in err

    def test_invalid_json_errors(self, repo, monkeypatch, capsys):
        write(repo, CONFIG, "{nope")
        monkeypatch.setenv("CICD_TRIGGER", "merge")
        with pytest.raises(SystemExit):
            bar.cmd_auto()
        assert "is not valid JSON" in capsys.readouterr().err

    def test_absent_config_is_merge(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bar, "SEMVER_CONFIG_PATH",
                            str(tmp_path / "missing.json"))
        assert bar.read_bump_on(bar.read_semver_config()) == "merge"

    def test_non_object_config_is_merge(self, tmp_path, monkeypatch):
        cfg = tmp_path / "c.json"
        cfg.write_text("[]")
        monkeypatch.setattr(bar, "SEMVER_CONFIG_PATH", str(cfg))
        assert bar.read_bump_on(bar.read_semver_config()) == "merge"

    def test_merge_value_takes_old_path(self, repo, monkeypatch):
        write(repo, CONFIG, json.dumps({"bump_on": "merge"}))
        monkeypatch.setenv("CICD_TRIGGER", "merge")
        called = []
        monkeypatch.setattr(bar, "handle_merge", lambda: called.append(1))
        monkeypatch.setattr(bar, "handle_tag_landed",
                            lambda t: pytest.fail("new mode used"))
        bar.cmd_auto()
        assert called == [1]

    def test_open_trigger_still_refused(self, repo, monkeypatch, capsys):
        monkeypatch.setenv("CICD_TRIGGER", "open")
        with pytest.raises(SystemExit):
            bar.cmd_auto()
        assert "does not run for trigger 'open'" in capsys.readouterr().err


class TestTagOnMergeProcess:
    def test_merge_run_as_subprocess_refuses_duplicate(self, repo):
        """The script as CI runs it: the duplicate-version refusal needs no push."""
        g(repo, "checkout", "-q", "-b", "other")
        write(repo, "VERSION", "1.1.0\n")
        other = commit(repo, "other")
        g(repo, "tag", "-a", "v1.1.0", "-m", "v1.1.0", other)
        g(repo, "checkout", "-q", "main")
        base = g(repo, "rev-parse", "HEAD")
        write(repo, "VERSION", "1.1.0\n")
        landed = commit(repo, "mine")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("CICD_", "GITHUB_", "INPUT_"))}
        env.update(CICD_TRIGGER="merge", CICD_BASE=base, CICD_HEAD=landed)
        result = subprocess.run([sys.executable, RELEASE], cwd=repo, env=env,
                                capture_output=True, text=True, check=False)
        assert result.returncode == 1
        assert f"already tagged at {other}" in result.stderr
