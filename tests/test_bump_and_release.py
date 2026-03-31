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
    def test_no_subcommand_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["semver"])
        with pytest.raises(SystemExit):
            bar.main()

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
