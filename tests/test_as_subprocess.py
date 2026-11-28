"""git-semver and release started as real processes, the way CI runs them.

These run the scripts through their `#!` line as subprocesses, so they cover
the `if __name__ == "__main__"` entry points and show that coverage counts a
script a test starts as a subprocess (`patch = ["subprocess"]` in
pyproject.toml).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
GIT_SEMVER = str(ROOT / "git-semver")
RELEASE = str(ROOT / "release")


def _env():
    """The test's environment without the CI variables release reads."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CICD_", "GITHUB_", "INPUT_"))}
    return env


def _run(cwd, *cmd):
    return subprocess.run([sys.executable, *cmd], cwd=cwd, env=_env(),
                          capture_output=True, text=True, check=False)


class TestGitSemverProcess:
    def test_version_prints_version(self, tmp_path):
        (tmp_path / ".semver").mkdir()
        (tmp_path / ".semver" / "config.json").write_text(
            json.dumps({"files": [], "updates": {}}))
        (tmp_path / "VERSION").write_text("1.4.2\n")
        result = _run(tmp_path, GIT_SEMVER, "--config", ".semver/config.json",
                      "version")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1.4.2"

    def test_error_names_the_problem_and_exits_1(self, tmp_path):
        (tmp_path / ".semver").mkdir()
        (tmp_path / ".semver" / "config.json").write_text(
            json.dumps({"files": [], "updates": {}}))
        result = _run(tmp_path, GIT_SEMVER, "--config", ".semver/config.json",
                      "version")
        assert result.returncode == 1
        assert result.stderr.startswith("Error: ")
        assert "VERSION" in result.stderr


class TestReleaseProcess:
    def test_unknown_subcommand_exits_1_with_usage(self, tmp_path):
        result = _run(tmp_path, RELEASE, "frobnicate")
        assert result.returncode == 1
        assert "Unknown subcommand: frobnicate" in result.stderr
        assert "Usage: release [bump|publish]" in result.stderr

    def test_no_subcommand_without_trigger_exits_1(self, tmp_path):
        result = _run(tmp_path, RELEASE)
        assert result.returncode == 1
        assert "needs CICD_TRIGGER" in result.stderr

    def test_open_trigger_refused(self, tmp_path):
        env = dict(_env(), CICD_TRIGGER="open")
        result = subprocess.run([sys.executable, RELEASE], cwd=tmp_path,
                                env=env, capture_output=True, text=True,
                                check=False)
        assert result.returncode == 1
        assert "does not run for trigger 'open' (from CICD_TRIGGER)" in result.stderr
