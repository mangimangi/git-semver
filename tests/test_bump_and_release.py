"""Tests for the bump-and-release CI orchestration script."""

import json
import types
from unittest.mock import MagicMock

import pytest

import bump_and_release as bar


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_result(stdout="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


@pytest.fixture
def mock_run(monkeypatch):
    """Replace bump_and_release.run with a recorder.

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

    def set_response(cmd_prefix, stdout="", returncode=0):
        responses[tuple(cmd_prefix)] = _make_result(stdout, returncode)

    monkeypatch.setattr(bar, "run", _run)
    return calls, set_response


@pytest.fixture
def env(monkeypatch):
    """Helper to set environment variables, clearing CI defaults."""
    cleared = [
        "GITHUB_EVENT_NAME", "GITHUB_EVENT_BEFORE", "GITHUB_SHA",
        "INPUT_BUMP_TYPE", "INPUT_SUBDIRECTORY", "INPUT_CHANGELOG_DESCRIPTION",
        "GH_TOKEN", "GITHUB_REPOSITORY",
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


# ── handle_push ─────────────────────────────────────────────────────────────

class TestHandlePush:
    def test_automerge_calls_bump_all_and_releases(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REPOSITORY="owner/repo",
            GITHUB_REF="refs/heads/main")
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="v1.0.1\nlatest\n")

        bar.handle_push(automerge=True)

        # Should call: configure_git (2), sync_branch (1), semver bump-all (1),
        # git tag (1), gh release create (1)
        cmds = [c[0] for c in calls]
        assert "git" in cmds         # git config calls
        assert bar.SEMVER_SCRIPT in cmds  # semver call

        # Check sync_branch was called (git pull --ff-only)
        pull_calls = [c for c in calls if c[:3] == ("git", "pull", "--ff-only")]
        assert len(pull_calls) == 1

        # Check semver was called with bump-all --since
        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 1
        assert semver_calls[0] == (bar.SEMVER_SCRIPT, "bump-all", "--since", "abc123")

        # Check release was created (not for 'latest')
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][:3] == ("gh", "release", "create")
        assert "v1.0.1" in gh_calls[0]

    def test_pr_mode_creates_pr_when_changes(self, mock_run, env):
        calls, set_response = mock_run
        env(
            GITHUB_EVENT_BEFORE="abc123",
            GITHUB_REF="refs/heads/main",
        )

        # rev-parse HEAD: first call returns pre_bump sha, second returns new sha
        rev_parse_results = iter(["pre_sha\n", "new_sha\n"])

        # Replace the mock_run's _run to handle multiple rev-parse calls
        original_calls = calls
        responses = {}

        def _run(*cmd, check=True, capture=True):
            original_calls.append(cmd)
            if cmd[:2] == ("git", "rev-parse") and cmd[2:] == ("HEAD",):
                return _make_result(stdout=next(rev_parse_results))
            if cmd[:2] == ("git", "log"):
                return _make_result(stdout="chore: bump version v1.0.1\n")
            return _make_result()

        import bump_and_release as bar_mod
        from unittest.mock import patch as mock_patch
        with mock_patch.object(bar_mod, "run", _run):
            bar.handle_push(automerge=False)

        # Check semver was called with --no-push
        semver_calls = [c for c in original_calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 1
        assert "--no-push" in semver_calls[0]

        # Check PR was created
        gh_calls = [c for c in original_calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        assert gh_calls[0][:3] == ("gh", "pr", "create")

    def test_pr_mode_skips_pr_when_no_changes(self, mock_run, env):
        calls, set_response = mock_run
        env(
            GITHUB_EVENT_BEFORE="abc123",
            GITHUB_REF="refs/heads/main",
        )
        # HEAD unchanged after bump-all (both rev-parse calls return same sha)
        set_response(["git", "rev-parse", "HEAD"], stdout="same_sha\n")

        bar.handle_push(automerge=False)

        # No PR created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 0

    def test_errors_when_before_not_set(self, mock_run, env):
        env()  # no GITHUB_EVENT_BEFORE
        with pytest.raises(SystemExit):
            bar.handle_push(automerge=True)

    def test_sync_branch_called_before_bump(self, mock_run, env):
        """Verify sync_branch runs before semver bump-all."""
        calls, set_response = mock_run
        env(GITHUB_EVENT_BEFORE="abc123", GITHUB_REPOSITORY="owner/repo",
            GITHUB_REF="refs/heads/main")
        set_response(["git", "tag", "--points-at", "HEAD"], stdout="")

        bar.handle_push(automerge=True)

        # Find indices of pull and semver calls
        pull_idx = next(i for i, c in enumerate(calls)
                        if c[:3] == ("git", "pull", "--ff-only"))
        semver_idx = next(i for i, c in enumerate(calls)
                          if c[0] == bar.SEMVER_SCRIPT)
        assert pull_idx < semver_idx


# ── handle_dispatch ─────────────────────────────────────────────────────────

class TestHandleDispatch:
    def test_automerge_with_bump_type(self, mock_run, env):
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="minor", GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"], stdout="v1.1.0\n")

        bar.handle_dispatch(automerge=True)

        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert len(semver_calls) == 1
        assert semver_calls[0] == (bar.SEMVER_SCRIPT, "bump", "minor")

        # Release created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1

    def test_automerge_with_subdir_and_description(self, mock_run, env):
        calls, set_response = mock_run
        env(
            INPUT_BUMP_TYPE="major",
            INPUT_SUBDIRECTORY="frontend",
            INPUT_CHANGELOG_DESCRIPTION="Breaking change",
            GITHUB_REPOSITORY="owner/repo",
        )
        set_response(["git", "tag", "--points-at", "HEAD"],
                     stdout="frontend/v2.0.0\n")

        bar.handle_dispatch(automerge=True)

        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert semver_calls[0] == (
            bar.SEMVER_SCRIPT, "bump", "major",
            "--subdir", "frontend",
            "--description", "Breaking change",
        )

    def test_pr_mode_creates_pr(self, mock_run, env):
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="patch")
        set_response(["git", "describe", "--tags", "--exact-match", "HEAD"],
                     stdout="v1.0.2\n")

        bar.handle_dispatch(automerge=False)

        # bump called with --no-push
        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert "--no-push" in semver_calls[0]

        # PR created
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) == 1
        pr_call = gh_calls[0]
        assert "--title" in pr_call
        # Find the title value
        title_idx = list(pr_call).index("--title") + 1
        assert "v1.0.2" in pr_call[title_idx]

    def test_pr_mode_handles_unknown_tag(self, mock_run, env):
        calls, set_response = mock_run
        env(INPUT_BUMP_TYPE="patch")
        set_response(["git", "describe", "--tags", "--exact-match", "HEAD"],
                     stdout="", returncode=128)

        bar.handle_dispatch(automerge=False)

        # Branch uses "unknown" fallback
        checkout_calls = [c for c in calls
                         if len(c) >= 3 and c[:2] == ("git", "checkout")]
        assert any("unknown" in c[3] for c in checkout_calls)

    def test_defaults_bump_type_to_patch(self, mock_run, env):
        calls, set_response = mock_run
        env(GITHUB_REPOSITORY="owner/repo")
        set_response(["git", "tag", "--points-at", "HEAD"], stdout="")

        bar.handle_dispatch(automerge=True)

        semver_calls = [c for c in calls if c[0] == bar.SEMVER_SCRIPT]
        assert semver_calls[0] == (bar.SEMVER_SCRIPT, "bump", "patch")


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


# ── main ────────────────────────────────────────────────────────────────────

class TestMain:
    def test_push_dispatches_to_handle_push(self, monkeypatch, env, tmp_path):
        env(GITHUB_EVENT_NAME="push", GITHUB_EVENT_BEFORE="abc")
        # Config with automerge=true
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        called_with = {}

        def fake_handle_push(automerge):
            called_with["automerge"] = automerge

        monkeypatch.setattr(bar, "handle_push", fake_handle_push)
        bar.main()
        assert called_with["automerge"] is True

    def test_dispatch_dispatches_to_handle_dispatch(self, monkeypatch, env, tmp_path):
        env(GITHUB_EVENT_NAME="workflow_dispatch")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": {"automerge": False}}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        called_with = {}

        def fake_handle_dispatch(automerge):
            called_with["automerge"] = automerge

        monkeypatch.setattr(bar, "handle_dispatch", fake_handle_dispatch)
        bar.main()
        assert called_with["automerge"] is False

    def test_push_skips_when_on_merge_false(self, monkeypatch, env, tmp_path, capsys):
        env(GITHUB_EVENT_NAME="push")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"install": {"on_merge": False}}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        bar.main()

        out = capsys.readouterr().out
        assert "on_merge is false" in out

    def test_unknown_event_exits(self, monkeypatch, env, tmp_path):
        env(GITHUB_EVENT_NAME="pull_request")
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({}))
        monkeypatch.setattr(bar, "CONFIG_PATH", str(cfg))

        with pytest.raises(SystemExit):
            bar.main()
