"""No release path creates, moves or force-pushes a `latest` tag.

Real local repositories: a bare `origin` whose pre-receive hook refuses any
change to an existing tag (what a forced tag push would be) and the creation
of `latest`, logging every ref update it accepts; and a clone that releases
into it. git-semver and release run as subprocesses; `gh` is a fake on PATH
that records its arguments. No token, no network.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
GIT_SEMVER = str(ROOT / "git-semver")
RELEASE = str(ROOT / "release")
CONFIG = ".vendored/configs/git-semver.json"
ZERO = "0" * 40

PRE_RECEIVE = """#!/bin/sh
while read old new ref; do
    case "$ref" in
        refs/tags/latest)
            echo "refused: $ref" >&2; exit 1 ;;
        refs/tags/*)
            if [ "$old" != "%s" ]; then
                echo "refused: $ref moved" >&2; exit 1
            fi ;;
    esac
    echo "$old $new $ref" >> "$GIT_DIR/pushes.log"
done
""" % ZERO


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
    g(repo, "commit", "-q", "-m", message)
    return g(repo, "rev-parse", "HEAD")


def tag_sha(repo, tag):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
        cwd=repo, capture_output=True, text=True)
    return result.stdout.strip() or None


@pytest.fixture
def world(tmp_path):
    """(origin, clone, env, gh_log) for a repo at 1.0.0 tagged v1.0.0."""
    origin = tmp_path / "origin.git"
    clone = tmp_path / "clone"
    bin_dir = tmp_path / "bin"
    gh_log = tmp_path / "gh.log"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\necho "$*" >> "{gh_log}"\n')
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    g(tmp_path, "clone", "-q", str(origin), str(clone))
    g(clone, "checkout", "-q", "-b", "main")
    write(clone, CONFIG, json.dumps({
        "version_file": "VERSION", "files": ["src/**"], "changelog": False,
    }))
    write(clone, "VERSION", "1.0.0\n")
    write(clone, "src/app.py", "a\n")
    commit(clone, "initial")
    g(clone, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    g(clone, "push", "-q", "origin", "main", "v1.0.0")
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(PRE_RECEIVE)
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CICD_", "GITHUB_", "INPUT_"))}
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    })
    return origin, clone, env, gh_log


def stale_latest(origin, clone):
    """A `latest` tag at v1.0.0 on origin and at a different commit in the
    clone, as an older git-semver left them: a `git push --tags` would fail
    and a forced one would move origin's."""
    hook = origin / "hooks" / "pre-receive"
    hook.rename(origin / "hooks" / "off")
    g(clone, "tag", "latest", "v1.0.0^{commit}")
    g(clone, "push", "-q", "origin", "refs/tags/latest")
    (origin / "hooks" / "off").rename(hook)
    old = tag_sha(origin, "latest")
    g(clone, "commit", "-q", "--allow-empty", "-m", "elsewhere")
    g(clone, "tag", "-f", "latest")
    g(clone, "reset", "-q", "--hard", "HEAD~1")
    local = tag_sha(clone, "latest")
    assert local != old
    return old, local


def change(clone):
    """Land a change to a configured file; returns the commit before it."""
    before = g(clone, "rev-parse", "HEAD")
    write(clone, "src/app.py", "b\n")
    commit(clone, "feat: change")
    g(clone, "push", "-q", "origin", "main")
    return before


def run(cmd, clone, env, **extra):
    result = subprocess.run([sys.executable, *cmd], cwd=clone,
                            env={**env, **extra}, capture_output=True,
                            text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def pushed_refs(origin):
    log = origin / "pushes.log"
    return [line.split()[2] for line in log.read_text().splitlines()] if log.exists() else []


def assert_no_latest(origin, clone, gh_log):
    assert tag_sha(origin, "latest") is None
    assert tag_sha(clone, "latest") is None
    assert "latest" not in (gh_log.read_text() if gh_log.exists() else "")


class TestBumpOnMerge:
    def test_git_semver_bump_pushes_tag_by_name_no_latest(self, world):
        origin, clone, env, gh_log = world
        change(clone)
        result = run([GIT_SEMVER, "bump", "patch"], clone, env)
        assert "Tagged: v1.0.1\n" in result.stdout
        assert "latest" not in result.stdout
        assert tag_sha(origin, "v1.0.1") == g(clone, "rev-parse", "HEAD")
        assert pushed_refs(origin)[-2:] == ["refs/heads/main", "refs/tags/v1.0.1"]
        assert_no_latest(origin, clone, gh_log)

    def test_release_bump_no_latest(self, world):
        origin, clone, env, gh_log = world
        before = change(clone)
        run([RELEASE, "bump"], clone, env, GITHUB_EVENT_NAME="push",
            GITHUB_EVENT_BEFORE=before, GITHUB_REF="refs/heads/main")
        head = g(clone, "rev-parse", "HEAD")
        assert tag_sha(origin, "v1.0.1") == head
        assert g(origin, "rev-parse", "main") == head
        assert "release create v1.0.1" in gh_log.read_text()
        assert_no_latest(origin, clone, gh_log)

    def test_release_no_subcommand_merge_no_latest(self, world):
        origin, clone, env, gh_log = world
        before = change(clone)
        run([RELEASE], clone, env, CICD_TRIGGER="merge", CICD_BASE=before,
            CICD_TARGET_BRANCH="main")
        assert tag_sha(origin, "v1.0.1") == g(clone, "rev-parse", "HEAD")
        assert_no_latest(origin, clone, gh_log)

    def test_existing_latest_left_alone(self, world):
        origin, clone, env, gh_log = world
        old, local = stale_latest(origin, clone)
        before = change(clone)
        run([RELEASE, "bump"], clone, env, GITHUB_EVENT_NAME="push",
            GITHUB_EVENT_BEFORE=before, GITHUB_REF="refs/heads/main")
        assert tag_sha(origin, "v1.0.1") == g(clone, "rev-parse", "HEAD")
        assert tag_sha(origin, "latest") == old
        assert tag_sha(clone, "latest") == local
        assert "refs/tags/latest" not in pushed_refs(origin)
        assert "latest" not in gh_log.read_text()

    def test_tag_push_existing_latest_left_alone(self, world):
        origin, clone, env, gh_log = world
        old, local = stale_latest(origin, clone)
        write(clone, "VERSION", "1.1.0\n")
        commit(clone, "chore: bump version to v1.1.0")
        g(clone, "push", "-q", "origin", "main")
        result = run([GIT_SEMVER, "tag", "--push"], clone, env)
        assert "Created tags: v1.1.0\n" in result.stdout
        assert tag_sha(origin, "v1.1.0") == g(clone, "rev-parse", "HEAD")
        assert tag_sha(origin, "latest") == old
        assert tag_sha(clone, "latest") == local


class TestTagOnMerge:
    def _pull_request_mode(self, clone):
        write(clone, CONFIG, json.dumps({
            "version_file": "VERSION", "files": ["src/**"], "changelog": False,
            "bump_on": "pull_request",
        }))

    def test_release_tags_landed_commit_no_latest(self, world):
        origin, clone, env, gh_log = world
        self._pull_request_mode(clone)
        before = g(clone, "rev-parse", "HEAD")
        write(clone, "VERSION", "1.1.0\n")
        landed = commit(clone, "feat: change (bumped)")
        g(clone, "push", "-q", "origin", "main")
        run([RELEASE], clone, env, CICD_TRIGGER="merge", CICD_BASE=before,
            CICD_HEAD=landed, CICD_TARGET_BRANCH="main")
        assert tag_sha(origin, "v1.1.0") == landed
        assert pushed_refs(origin)[-1] == "refs/tags/v1.1.0"
        assert_no_latest(origin, clone, gh_log)

    def test_existing_latest_left_alone(self, world):
        origin, clone, env, gh_log = world
        old, local = stale_latest(origin, clone)
        self._pull_request_mode(clone)
        before = g(clone, "rev-parse", "HEAD")
        write(clone, "VERSION", "1.1.0\n")
        landed = commit(clone, "feat: change (bumped)")
        g(clone, "push", "-q", "origin", "main")
        run([RELEASE], clone, env, CICD_TRIGGER="merge", CICD_BASE=before,
            CICD_HEAD=landed, CICD_TARGET_BRANCH="main")
        assert tag_sha(origin, "v1.1.0") == landed
        assert tag_sha(origin, "latest") == old
        assert tag_sha(clone, "latest") == local
        assert "latest" not in gh_log.read_text()


def test_scripts_never_force_or_move_latest():
    """No `tag -f`, `--force` push or `latest` tag call is left in the code."""
    for script in (GIT_SEMVER, RELEASE):
        text = Path(script).read_text()
        assert '"tag", "-f"' not in text
        assert '"--force"' not in text
        assert '"push", "--tags"' not in text
