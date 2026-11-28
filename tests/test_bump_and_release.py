"""Tests for the semver CI orchestration script."""

import json
import sys
import types
from unittest.mock import MagicMock, patch as mock_patch

import pytest

import semver_script as bar


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_result(stdout="", stderr="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


@pytest.fixture(autouse=True)
def default_bump_on(tmp_path, monkeypatch):
    """Keep these tests on the default bump-on-merge path.

    release reads "bump_on" from git-semver's config relative to the working
    directory, which for these tests is this repository, whose own config
    selects "pull_request". Point it at a missing file so the tests exercise
    the default, as a repository without the setting would.
    """
    monkeypatch.setattr(bar, "SEMVER_CONFIG_PATH",
                        str(tmp_path / "no-git-semver-config.json"))


@pytest.fixture
def mock_run(monkeypatch):
    """Replace semver_script.run with a recorder.

    Returns (calls, set_response).
      calls:        list of command tuples captured
      set_response: register a return value for a command prefix
    """
    calls = []
    responses = {}

    def _run(*cmd, check=True, capture=True):
        calls.append(cmd)
        for length in range(len(cmd), 0, -1):
            key = cmd[:length]
            if key in responses:
                return responses[key]
        return _make_result()

    def set_response(cmd_prefix, stdout="", stderr="", returncode=0):
        responses[tuple(cmd_prefix)] = _make_result(stdout, stderr, returncode)

    monkeypatch.setattr(bar, "run", _run)
    return calls, set_response


@pytest.fixture
def env(monkeypatch):
    """Helper to set environment variables, clearing CI defaults."""
    cleared = [
        "GITHUB_EVENT_NAME", "GITHUB_EVENT_BEFORE", "GITHUB_SHA",
        "INPUT_BUMP_TYPE", "INPUT_SUBDIRECTORY", "INPUT_CHANGELOG_DESCRIPTION",
        "GH_TOKEN", "GITHUB_REPOSITORY", "GITHUB_REF",
        "CICD_TRIGGER", "CICD_BASE", "CICD_HEAD", "CICD_TARGET_BRANCH",
        "CICD_SOURCE_BRANCH", "CICD_JOB", "CICD_CHANGED_FILES",
        "CICD_INPUT_BUMP_TYPE", "CICD_INPUT_SUBDIRECTORY",
        "CICD_INPUT_CHANGELOG_DESCRIPTION",
    ]
    for key in cleared:
        monkeypatch.delenv(key, raising=False)

    def _set(**kwargs):
        for k, v in kwargs.items():
            monkeypatch.setenv(k, v)

    return _set


# ── read_config ─────────────────────────────────────────────────────────────

class TestReadConfig:
    def test_defaults_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bar, "CONFIG_PATH", str(tmp_path / "missing.json"))
        assert bar.read_config() == (True, True)

    def test_defaults_when_no_install_key(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"version_file": "VERSION"}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))
        assert bar.read_config() == (True, True)

    def test_reads_on_merge_and_automerge(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "install": {"on_merge": False, "automerge": False}
        }))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))
        assert bar.read_config() == (False, False)

    def test_partial_install_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": {"automerge": False}}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))
        assert bar.read_config() == (True, False)

    def test_handles_invalid_json(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text("not json")
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))
        assert bar.read_config() == (True, True)


# ── sync_branch ─────────────────────────────────────────────────────────────

class TestSyncBranch:
    def test_pulls_ff_only(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REF="refs/heads/main")

        bar.sync_branch()

        pull_calls = [c for c in calls if c[:3] == ("git", "pull", "--ff-only")]
        assert len(pull_calls) == 1
        assert pull_calls[0] == ("git", "pull", "--ff-only", "origin", "main")

    def test_uses_branch_from_github_ref(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REF="refs/heads/master")

        bar.sync_branch()

        pull_calls = [c for c in calls if c[:3] == ("git", "pull", "--ff-only")]
        assert pull_calls[0][-1] == "master"

    def test_defaults_to_main(self, mock_run, env):
        calls, set_response = mock_run
        env()  # no GITHUB_REF

        bar.sync_branch()

        pull_calls = [c for c in calls if c[:3] == ("git", "pull", "--ff-only")]
        assert pull_calls[0][-1] == "main"

    def test_continues_on_pull_failure(self, mock_run, env, capsys):
        calls, set_response = mock_run
        env(GITHUB_REF="refs/heads/main")
        set_response(["git", "pull", "--ff-only", "origin", "main"], returncode=1)

        bar.sync_branch()  # Should not raise

        out = capsys.readouterr().out
        assert "Warning" in out
        assert "could not fast-forward" in out


# ── is_protected_branch_error ──────────────────────────────────────────────

class TestIsProtectedBranchError:
    def test_gh006_detected(self):
        result = _make_result(stderr="remote: error: GH006: Protected branch")
        assert bar.is_protected_branch_error(result) is True

    def test_protected_branch_text_detected(self):
        result = _make_result(stderr="refusing to push to protected branch")
        assert bar.is_protected_branch_error(result) is True

    def test_other_error_not_detected(self):
        result = _make_result(stderr="fatal: remote rejected")
        assert bar.is_protected_branch_error(result) is False

    def test_empty_stderr(self):
        result = _make_result(stderr="")
        assert bar.is_protected_branch_error(result) is False


# ── try_push_or_pr ─────────────────────────────────────────────────────────

class TestTryPushOrPr:
    def test_successful_push(self, mock_run, env):
        calls, set_response = mock_run
        set_response(["git", "push"], stdout="", returncode=0)

        result = bar.try_push_or_pr("chore: bump version v1.0.1")
        assert result is True

        # No PR created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 0

    def test_protected_branch_falls_back_to_pr(self, mock_run, env):
        calls, set_response = mock_run
        set_response(["git", "push"],
                     stderr="remote: error: GH006: Protected branch",
                     returncode=1)

        result = bar.try_push_or_pr("chore: bump version v1.0.1")
        assert result is False

        # PR created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][:3] == ("gh", "pr", "create")

    def test_non_protection_error_exits(self, mock_run, env):
        calls, set_response = mock_run
        set_response(["git", "push"],
                     stderr="fatal: network error",
                     returncode=1)

        with pytest.raises(SystemExit):
            bar.try_push_or_pr("chore: bump version v1.0.1")


# ── handle_push_bump ──────────────────────────────────────────────────────

class TestHandlePushBump:
    def test_automerge_bumps_pushes_and_tags_inline(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REPOSITORY="owner/repo",
            GITHUB_REF="refs/heads/main")

        # rev-parse returns different SHAs (bump happened)
        rev_parse_results = iter(["pre_sha\n", "new_sha\n"])

        original_calls = calls

        def _run(*cmd, check=True, capture=True):
            original_calls.append(cmd)
            if cmd[:2] == ("git", "rev-parse") and cmd[2:] == ("HEAD",):
                return _make_result(stdout=next(rev_parse_results))
            if cmd[:2] == ("git", "log"):
                return _make_result(stdout="chore: bump version v1.0.1\n")
            if cmd[:2] == ("git", "push") and len(cmd) == 2:
                return _make_result(returncode=0)
            if cmd[:3] == ("git", "tag", "--points-at"):
                return _make_result(stdout="v1.0.1\nlatest\n")
            return _make_result()

        with mock_patch.object(bar, "run", _run):
            bar.handle_push_bump(automerge=True)

        # Check git-semver was called with --no-push first, then tag --push
        semver_calls = [c for c in original_calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 2
        assert "--no-push" in semver_calls[0]
        assert "--since" in semver_calls[0]
        assert semver_calls[1] == (bar.SEMVER_SCRIPT, "tag", "--push")

        # Check git push was attempted (automerge=True)
        push_calls = [c for c in original_calls
                      if c[:2] == ("git", "push") and len(c) == 2]
        assert len(push_calls) == 1

        # Check GitHub release created (not for 'latest')
        gh_calls = [c for c in original_calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert "v1.0.1" in gh_calls[0]

    def test_automerge_protected_branch_falls_back_to_pr_no_tag(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REF="refs/heads/main")

        rev_parse_results = iter(["pre_sha\n", "new_sha\n"])
        original_calls = calls

        def _run(*cmd, check=True, capture=True):
            original_calls.append(cmd)
            if cmd[:2] == ("git", "rev-parse") and cmd[2:] == ("HEAD",):
                return _make_result(stdout=next(rev_parse_results))
            if cmd[:2] == ("git", "log"):
                return _make_result(stdout="chore: bump version v1.0.1\n")
            if cmd[:2] == ("git", "push") and len(cmd) == 2:
                return _make_result(
                    stderr="remote: error: GH006: Protected branch",
                    returncode=1)
            return _make_result()

        with mock_patch.object(bar, "run", _run):
            bar.handle_push_bump(automerge=True)

        # PR created after protected branch rejection
        gh_calls = [c for c in original_calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][:3] == ("gh", "pr", "create")

        # No inline tagging — publish job handles it after PR merge
        semver_calls = [c for c in original_calls if c[0] == bar.SEMVER_SCRIPT]
        tag_calls = [c for c in semver_calls if "tag" in c]
        assert len(tag_calls) == 0

    def test_pr_mode_creates_pr_when_changes(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REF="refs/heads/main")

        rev_parse_results = iter(["pre_sha\n", "new_sha\n"])
        original_calls = calls

        def _run(*cmd, check=True, capture=True):
            original_calls.append(cmd)
            if cmd[:2] == ("git", "rev-parse") and cmd[2:] == ("HEAD",):
                return _make_result(stdout=next(rev_parse_results))
            if cmd[:2] == ("git", "log"):
                return _make_result(stdout="chore: bump version v1.0.1\n")
            return _make_result()

        with mock_patch.object(bar, "run", _run):
            bar.handle_push_bump(automerge=False)

        # Check --no-push used
        semver_calls = [c for c in original_calls if c[0] == bar.SEMVER_SCRIPT]
        assert "--no-push" in semver_calls[0]

        # PR created (no push attempt with automerge=False)
        gh_calls = [c for c in original_calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][:3] == ("gh", "pr", "create")

        # No git push attempted
        push_calls = [c for c in original_calls
                      if c[:2] == ("git", "push") and len(c) == 2]
        assert len(push_calls) == 0

    def test_pr_mode_skips_pr_when_no_changes(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REF="refs/heads/main")
        # HEAD unchanged (no bump)
        set_response(["git", "rev-parse", "HEAD"], stdout="same_sha\n")

        bar.handle_push_bump(automerge=False)

        # No PR created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 0

    def test_errors_when_before_not_set(self, mock_run, env):
        env()  # no GITHUB_EVENT_BEFORE
        with pytest.raises(SystemExit):
            bar.handle_push_bump(automerge=True)

    def test_sync_branch_called_before_bump(self, mock_run, env):
        """Verify sync_branch runs before git-semver bump-all."""
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REPOSITORY="owner/repo",
            GITHUB_REF="refs/heads/main")
        # Same SHA = no bump, simplifies test
        set_response(["git", "rev-parse", "HEAD"], stdout="same\n")

        bar.handle_push_bump(automerge=True)

        # Find indices of pull and semver calls
        pull_idx = next(i for i, c in enumerate(calls)
                        if c[:3] == ("git", "pull", "--ff-only"))
        semver_idx = next(i for i, c in enumerate(calls)
                          if c[0] == bar.SEMVER_SCRIPT)
        assert pull_idx < semver_idx


# ── handle_dispatch_bump ──────────────────────────────────────────────────

class TestHandleDispatchBump:
    def test_automerge_bumps_pushes_and_tags_inline(self, mock_run, env):
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="minor", GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "log", "-1", "--pretty=%s"],
                     stdout="chore: bump version to v1.1.0\n")
        set_response(["git", "push"], returncode=0)
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="v1.1.0\nlatest\n")

        bar.handle_dispatch_bump(automerge=True)

        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 2
        # First call: bump --no-push
        assert "--no-push" in semver_calls[0]
        assert "minor" in semver_calls[0]
        # Second call: tag --push
        assert semver_calls[1] == (bar.SEMVER_SCRIPT, "tag", "--push")

        # Push attempted
        push_calls = [c for c in calls
                      if c[:2] == ("git", "push") and len(c) == 2]
        assert len(push_calls) == 1

        # Release created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert "v1.1.0" in gh_calls[0]

    def test_automerge_with_subdir_and_description(self, mock_run, env):
        calls, set_response = mock_run
        env(
            INPUT_BUMP_TYPE="major",
            INPUT_SUBDIRECTORY="frontend",
            INPUT_CHANGELOG_DESCRIPTION="Breaking change",
            GITHUB_REPOSITORY="owner/repo",
        )
        set_response(["git", "log", "-1", "--pretty=%s"],
                     stdout="chore: bump version to frontend/v2.0.0\n")
        set_response(["git", "push"], returncode=0)
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="frontend/v2.0.0\nlatest\n")

        bar.handle_dispatch_bump(automerge=True)

        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert (
            bar.SEMVER_SCRIPT, "bump", "major", "--no-push",
            "--subdir", "frontend",
            "--description", "Breaking change",
        ) == semver_calls[0]
        assert semver_calls[1] == (bar.SEMVER_SCRIPT, "tag", "--push")

    def test_pr_mode_creates_pr(self, mock_run, env):
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="patch")
        set_response(["git", "describe", "--tags", "--exact-match", "HEAD"],
                     stdout="v1.0.2\n")

        bar.handle_dispatch_bump(automerge=False)

        # bump called with --no-push
        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert "--no-push" in semver_calls[0]

        # PR created (no push attempt)
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        pr_call = gh_calls[0]
        assert "--title" in pr_call
        title_idx = list(pr_call).index("--title") + 1
        assert "v1.0.2" in pr_call[title_idx]

        # No git push attempted
        push_calls = [c for c in calls
                      if c[:2] == ("git", "push") and len(c) == 2]
        assert len(push_calls) == 0

    def test_pr_mode_handles_unknown_tag(self, mock_run, env):
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="patch")
        set_response(["git", "describe", "--tags", "--exact-match", "HEAD"],
                     stdout="", returncode=128)

        bar.handle_dispatch_bump(automerge=False)

        # Branch uses "unknown" fallback
        checkout_calls = [c for c in calls
                         if len(c) >= 3 and c[:2] == ("git", "checkout")]
        assert any("unknown" in c[3] for c in checkout_calls)

    def test_defaults_bump_type_to_patch(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "log", "-1", "--pretty=%s"],
                     stdout="chore: bump version to v1.0.1\n")
        set_response(["git", "push"], returncode=0)
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="v1.0.1\nlatest\n")

        bar.handle_dispatch_bump(automerge=True)

        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert "patch" in semver_calls[0]

    def test_dispatch_protected_branch_falls_back_no_tag(self, mock_run, env):
        """Dispatch with automerge=True falls back to PR on protected branch — no inline tagging."""
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="patch")
        set_response(["git", "log", "-1", "--pretty=%s"],
                     stdout="chore: bump version to v1.0.1\n")
        set_response(["git", "push"],
                     stderr="remote: error: GH006: Protected branch",
                     returncode=1)

        bar.handle_dispatch_bump(automerge=True)

        # PR created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][:3] == ("gh", "pr", "create")

        # No inline tagging — publish job handles it after PR merge
        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        tag_calls = [c for c in semver_calls if "tag" in c]
        assert len(tag_calls) == 0


# ── create_releases ─────────────────────────────────────────────────────────

class TestCreateReleases:
    def test_creates_release_per_tag(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="v1.0.0\nfrontend/v2.0.0\nlatest\n")

        bar.create_releases()

        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 2
        tags_created = [c[3] for c in gh_calls]  # gh release create <tag>
        assert "v1.0.0" in tags_created
        assert "frontend/v2.0.0" in tags_created
        assert "latest" not in tags_created

    def test_no_tags_no_releases(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"], stdout="\n")

        bar.create_releases()

        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 0


# ── git_semver helper ──────────────────────────────────────────────────────

class TestGitSemver:
    def test_passes_capture_false_to_run(self, monkeypatch):
        """git_semver() must pass capture=False so git-semver output is visible in CI."""
        captured_kwargs = {}

        def _run(*cmd, check=True, capture=True):
            captured_kwargs["capture"] = capture
            return _make_result()

        monkeypatch.setattr(bar, "run", _run)
        bar.git_semver("bump-all", "--since", "abc123")
        assert captured_kwargs["capture"] is False


# ── cmd_bump ──────────────────────────────────────────────────────────────

class TestCmdBump:
    def test_push_dispatches_to_handle_push_bump(self, monkeypatch, env, tmp_path):
        env(GITHUB_EVENT_NAME="push", GITHUB_EVENT_BEFORE="abc")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        called_with = {}

        def fake_handle_push_bump(automerge):
            called_with["automerge"] = automerge

        monkeypatch.setattr(bar, "handle_push_bump", fake_handle_push_bump)
        bar.cmd_bump()
        assert called_with["automerge"] is True

    def test_dispatch_dispatches_to_handle_dispatch_bump(self, monkeypatch, env, tmp_path):
        env(GITHUB_EVENT_NAME="workflow_dispatch")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": {"automerge": False}}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        called_with = {}

        def fake_handle_dispatch_bump(automerge):
            called_with["automerge"] = automerge

        monkeypatch.setattr(bar, "handle_dispatch_bump", fake_handle_dispatch_bump)
        bar.cmd_bump()
        assert called_with["automerge"] is False

    def test_push_skips_when_on_merge_false(self, monkeypatch, env, tmp_path, capsys):
        env(GITHUB_EVENT_NAME="push")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": {"on_merge": False}}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        bar.cmd_bump()

        out = capsys.readouterr().out
        assert "on_merge is false" in out

    def test_unknown_event_exits(self, monkeypatch, env, tmp_path):
        env(GITHUB_EVENT_NAME="pull_request")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        with pytest.raises(SystemExit):
            bar.cmd_bump()


# ── cmd_publish ───────────────────────────────────────────────────────────

class TestCmdPublish:
    def test_calls_tag_push_and_releases(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="v1.0.1\nlatest\n")

        bar.cmd_publish()

        # git-semver tag --push called
        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 1
        assert semver_calls[0] == (bar.SEMVER_SCRIPT, "tag", "--push")

        # Release created (not for latest)
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert "v1.0.1" in gh_calls[0]

    def test_publish_with_multiple_components(self, mock_run, env):
        """Monorepo: creates releases for all component tags."""
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="v1.0.1\nfrontend/v2.0.0\nlatest\n")

        bar.cmd_publish()

        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 2
        tags_created = [c[3] for c in gh_calls]
        assert "v1.0.1" in tags_created
        assert "frontend/v2.0.0" in tags_created
        assert "latest" not in tags_created

    def test_publish_noop_when_no_tags(self, mock_run, env):
        """No version tags created = no releases, exits cleanly."""
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"], stdout="\n")

        bar.cmd_publish()  # Should not raise

        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 0

    def test_publish_skips_latest_tag(self, mock_run, env):
        """Only version tags get releases, not 'latest'."""
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="latest\n")

        bar.cmd_publish()

        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 0


# ── main ──────────────────────────────────────────────────────────────────

class TestMain:
    def test_no_subcommand_without_trigger_exits_with_reason(
            self, monkeypatch, mock_run, env, capsys):
        # No subcommand is now the auto entry point; with no trigger
        # variables it still refuses, naming what is missing.
        calls, _ = mock_run
        env()
        monkeypatch.setattr(sys, "argv", ["semver"])
        with pytest.raises(SystemExit) as exc:
            bar.main()
        assert exc.value.code != 0
        assert "CICD_TRIGGER" in capsys.readouterr().err
        assert calls == []

    def test_unknown_subcommand_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["semver", "unknown"])
        with pytest.raises(SystemExit):
            bar.main()

    def test_bump_subcommand(self, monkeypatch, env, tmp_path):
        monkeypatch.setattr(sys, "argv", ["semver", "bump"])
        env(GITHUB_EVENT_NAME="push")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": {"on_merge": False}}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        bar.main()  # Should not raise (on_merge=false skips)

    def test_publish_subcommand(self, monkeypatch, mock_run, env):
        monkeypatch.setattr(sys, "argv", ["semver", "publish"])
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"], stdout="\n")

        bar.main()

        # git-semver tag --push called
        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 1


# ── release with no subcommand ────────────────────────────────────────────

def _auto_run(calls, subject, *, bumped=True, push_stderr="", push_code=0,
              tags="v1.0.1\nlatest\n"):
    """A fake run(): landed commit `subject`; bump-all moves HEAD when `bumped`."""
    rev_parse = iter(["pre_sha\n", "new_sha\n" if bumped else "pre_sha\n"])

    def _run(*cmd, check=True, capture=True):
        calls.append(cmd)
        if cmd[:4] == ("git", "log", "-1", "--format=%s"):
            return _make_result(stdout=subject + "\n")
        if cmd[:2] == ("git", "rev-parse") and cmd[2:] == ("HEAD",):
            return _make_result(stdout=next(rev_parse))
        if cmd[:3] == ("git", "log", "-1"):
            return _make_result(stdout="chore: bump version v1.0.1\n")
        if cmd[:2] == ("git", "push") and len(cmd) == 2:
            return _make_result(stderr=push_stderr, returncode=push_code)
        if cmd[:3] == ("git", "tag", "--points-at"):
            return _make_result(stdout=tags)
        if cmd[:3] == ("git", "describe", "--tags"):
            return _make_result(stdout="v1.1.0\n")
        return _make_result()

    return _run


def _semver(calls):
    return [c[1:] for c in calls if c[0] == bar.SEMVER_SCRIPT]


def _gh(calls):
    return [c for c in calls if c[0] == "gh"]


def _pushes(calls):
    return [c for c in calls if c[:2] == ("git", "push") and len(c) == 2]


@pytest.fixture
def config(tmp_path, monkeypatch):
    def _write(install=None):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": install} if install else {}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))
    _write()
    return _write


@pytest.fixture
def auto(monkeypatch):
    """Run `release` with no subcommand against a fake run(); return calls."""
    def _go(subject="feat: something", **kwargs):
        calls = []
        monkeypatch.setattr(bar, "run", _auto_run(calls, subject, **kwargs))
        monkeypatch.setattr(sys, "argv", ["release"])
        bar.main()
        return calls
    return _go


class TestAutoMerge:
    def test_bump_commit_publishes(self, auto, env, config):
        env(CICD_TRIGGER="merge", CICD_BASE="base", CICD_HEAD="head",
            GITHUB_REPOSITORY="owner/repo")
        calls = auto("chore: bump version to v1.0.1 (#12)")

        assert ("git", "log", "-1", "--format=%s", "head") in calls
        assert _semver(calls) == [("tag", "--push")]
        assert [c[3] for c in _gh(calls)] == ["v1.0.1"]
        assert _pushes(calls) == []

    def test_install_commit_does_nothing(self, auto, env, config, capsys):
        env(CICD_TRIGGER="merge", CICD_BASE="base", CICD_HEAD="head")
        calls = auto("chore: install git-semver v0.0.15 (#88)")

        assert calls == [("git", "log", "-1", "--format=%s", "head")]
        assert "nothing to do" in capsys.readouterr().out

    def test_ordinary_commit_bumps_pushes_tags_releases(self, auto, env, config):
        env(CICD_TRIGGER="merge", CICD_BASE="base123", CICD_HEAD="head",
            CICD_TARGET_BRANCH="main", GITHUB_REPOSITORY="owner/repo")
        calls = auto("feat: add thing (#5)")

        assert _semver(calls) == [
            ("bump-all", "--since", "base123", "--no-push"),
            ("tag", "--push"),
        ]
        assert len(_pushes(calls)) == 1
        assert [c[3] for c in _gh(calls)] == ["v1.0.1"]

    def test_no_configured_file_changed_no_bump(self, auto, env, config):
        env(CICD_TRIGGER="merge", CICD_BASE="base", CICD_HEAD="head")
        calls = auto("docs: typo", bumped=False)

        assert _semver(calls) == [("bump-all", "--since", "base", "--no-push")]
        assert _pushes(calls) == []
        assert _gh(calls) == []

    def test_on_merge_false_skips(self, auto, env, config, capsys):
        config({"on_merge": False})
        env(CICD_TRIGGER="merge", CICD_BASE="base", CICD_HEAD="head")
        calls = auto("feat: x")

        assert _semver(calls) == []
        assert "on_merge is false" in capsys.readouterr().out

    def test_automerge_false_opens_pr(self, auto, env, config):
        config({"automerge": False})
        env(CICD_TRIGGER="merge", CICD_BASE="base", CICD_HEAD="head")
        calls = auto("feat: x")

        assert _pushes(calls) == []
        checkout = [c for c in calls if c[:3] == ("git", "checkout", "-b")]
        assert checkout and checkout[0][3].startswith("chore/bump-version-")
        assert _gh(calls)[0][:3] == ("gh", "pr", "create")
        assert ("tag", "--push") not in _semver(calls)

    def test_protected_branch_falls_back_to_pr_no_tag(self, auto, env, config):
        env(CICD_TRIGGER="merge", CICD_BASE="base", CICD_HEAD="head")
        calls = auto("feat: x", push_code=1,
                     push_stderr="remote: error: GH006: Protected branch")

        assert _gh(calls)[0][:3] == ("gh", "pr", "create")
        assert ("tag", "--push") not in _semver(calls)

    def test_missing_base_errors(self, auto, env, config, capsys):
        env(CICD_TRIGGER="merge", CICD_HEAD="head")
        with pytest.raises(SystemExit) as exc:
            auto("feat: x")
        assert exc.value.code != 0
        assert "CICD_BASE" in capsys.readouterr().err

    def test_github_push_variables(self, auto, env, config):
        env(GITHUB_EVENT_NAME="push", GITHUB_EVENT_BEFORE="before1",
            GITHUB_SHA="sha1", GITHUB_REPOSITORY="owner/repo")
        calls = auto("feat: x")

        assert ("git", "log", "-1", "--format=%s", "sha1") in calls
        assert _semver(calls)[0] == ("bump-all", "--since", "before1", "--no-push")

    def test_github_push_bump_commit_publishes(self, auto, env, config):
        env(GITHUB_EVENT_NAME="push", GITHUB_EVENT_BEFORE="before1",
            GITHUB_REPOSITORY="owner/repo")
        calls = auto("chore: bump version v1.0.1")

        assert ("git", "log", "-1", "--format=%s", "HEAD") in calls
        assert _semver(calls) == [("tag", "--push")]

    def test_cicd_base_wins_over_github_before(self, auto, env, config):
        env(CICD_TRIGGER="merge", CICD_BASE="cicd_base", CICD_HEAD="cicd_head",
            GITHUB_EVENT_NAME="push", GITHUB_EVENT_BEFORE="gh_before",
            GITHUB_SHA="gh_sha")
        calls = auto("feat: x")

        assert ("git", "log", "-1", "--format=%s", "cicd_head") in calls
        assert _semver(calls)[0] == ("bump-all", "--since", "cicd_base", "--no-push")

    def test_sync_uses_cicd_target_branch(self, auto, env, config):
        env(CICD_TRIGGER="merge", CICD_BASE="b", CICD_HEAD="h",
            CICD_TARGET_BRANCH="release-1", GITHUB_REF="refs/heads/main")
        calls = auto("feat: x", bumped=False)

        pulls = [c for c in calls if c[:3] == ("git", "pull", "--ff-only")]
        assert pulls == [("git", "pull", "--ff-only", "origin", "release-1")]


class TestAutoManual:
    @pytest.mark.parametrize("bump_type", ["patch", "minor", "major"])
    def test_cicd_bump_type(self, auto, env, config, bump_type):
        env(CICD_TRIGGER="manual", CICD_INPUT_BUMP_TYPE=bump_type,
            CICD_INPUT_SUBDIRECTORY="", CICD_INPUT_CHANGELOG_DESCRIPTION="")
        calls = auto()

        assert _semver(calls)[0] == ("bump", bump_type, "--no-push")

    def test_cicd_subdirectory_and_description(self, auto, env, config):
        env(CICD_TRIGGER="manual", CICD_INPUT_BUMP_TYPE="minor",
            CICD_INPUT_SUBDIRECTORY="backend",
            CICD_INPUT_CHANGELOG_DESCRIPTION="New API")
        calls = auto()

        assert _semver(calls)[0] == (
            "bump", "minor", "--no-push",
            "--subdir", "backend", "--description", "New API")
        assert len(_pushes(calls)) == 1
        assert ("tag", "--push") in _semver(calls)

    def test_defaults_to_patch(self, auto, env, config):
        env(CICD_TRIGGER="manual")
        calls = auto()

        assert _semver(calls)[0] == ("bump", "patch", "--no-push")

    def test_empty_bump_type_defaults_to_patch(self, auto, env, config):
        env(CICD_TRIGGER="manual", CICD_INPUT_BUMP_TYPE="")
        calls = auto()

        assert _semver(calls)[0] == ("bump", "patch", "--no-push")

    def test_github_dispatch_inputs(self, auto, env, config):
        env(GITHUB_EVENT_NAME="workflow_dispatch", INPUT_BUMP_TYPE="major",
            INPUT_SUBDIRECTORY="web", INPUT_CHANGELOG_DESCRIPTION="Big")
        calls = auto()

        assert _semver(calls)[0] == (
            "bump", "major", "--no-push",
            "--subdir", "web", "--description", "Big")

    def test_cicd_inputs_win_over_github_inputs(self, auto, env, config):
        env(CICD_TRIGGER="manual", CICD_INPUT_BUMP_TYPE="minor",
            CICD_INPUT_SUBDIRECTORY="",
            INPUT_BUMP_TYPE="major", INPUT_SUBDIRECTORY="web")
        calls = auto()

        assert _semver(calls)[0] == ("bump", "minor", "--no-push")

    def test_automerge_false_opens_pr(self, auto, env, config):
        config({"automerge": False})
        env(CICD_TRIGGER="manual", CICD_INPUT_BUMP_TYPE="minor")
        calls = auto()

        assert _pushes(calls) == []
        assert _gh(calls)[0][:3] == ("gh", "pr", "create")


class TestAutoTrigger:
    def test_cicd_trigger_wins_over_github_event(self, auto, env, config):
        env(CICD_TRIGGER="manual", GITHUB_EVENT_NAME="push",
            GITHUB_EVENT_BEFORE="before")
        calls = auto()

        assert _semver(calls)[0][0] == "bump"

    @pytest.mark.parametrize("trigger", ["open", "cron"])
    def test_other_cicd_triggers_refused(self, auto, env, config, capsys, trigger):
        env(CICD_TRIGGER=trigger)
        with pytest.raises(SystemExit) as exc:
            calls = auto()
        assert exc.value.code != 0
        err = capsys.readouterr().err
        assert repr(trigger) in err and "CICD_TRIGGER" in err

    def test_refused_trigger_runs_nothing(self, monkeypatch, mock_run, env, config):
        calls, _ = mock_run
        env(CICD_TRIGGER="cron")
        monkeypatch.setattr(sys, "argv", ["release"])
        with pytest.raises(SystemExit):
            bar.main()
        assert calls == []

    def test_unknown_github_event_refused(self, auto, env, config, capsys):
        env(GITHUB_EVENT_NAME="pull_request")
        with pytest.raises(SystemExit) as exc:
            auto()
        assert exc.value.code != 0
        assert "'pull_request'" in capsys.readouterr().err


# ── run (the real subprocess wrapper) ───────────────────────────────────────

class TestRun:
    def test_returns_captured_result(self):
        result = bar.run(sys.executable, "-c", "print('hi')")
        assert result.returncode == 0
        assert result.stdout == "hi\n"

    def test_failure_exits_1_naming_command_and_stderr(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            bar.run(sys.executable, "-c",
                    "import sys; sys.stderr.write('boom\\n'); sys.exit(3)")
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert f"Command failed: {sys.executable} -c" in err
        assert "boom" in err

    def test_failure_with_empty_stderr_names_only_command(self, capsys):
        with pytest.raises(SystemExit):
            bar.run(sys.executable, "-c", "import sys; sys.exit(2)")
        err = capsys.readouterr().err
        assert err.startswith("Command failed: ")
        assert err.count("\n") == 1

    def test_check_false_returns_failure(self):
        result = bar.run(sys.executable, "-c", "import sys; sys.exit(4)",
                         check=False)
        assert result.returncode == 4

    def test_uncaptured_failure_prints_no_stderr(self, capfd):
        with pytest.raises(SystemExit):
            bar.run(sys.executable, "-c", "import sys; sys.exit(5)",
                    capture=False)
        assert capfd.readouterr().err.startswith("Command failed: ")
