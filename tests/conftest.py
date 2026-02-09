"""Shared fixtures for git-semver tests."""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Import git-semver as a module ───────────────────────────────────────────

ROOT = Path(__file__).parent.parent


def _import_git_semver():
    """Import the git-semver script (no .py extension) as a Python module."""
    filepath = str(ROOT / "git-semver")
    loader = importlib.machinery.SourceFileLoader("git_semver", filepath)
    spec = importlib.util.spec_from_loader("git_semver", loader, origin=filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules["git_semver"] = module
    spec.loader.exec_module(module)
    return module


_import_git_semver()


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """Create a temporary directory simulating a repo and chdir into it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".semver").mkdir()
    return tmp_path


@pytest.fixture
def make_config(tmp_repo):
    """Write a config.json and return its path as a string."""
    def _make(config_dict, path=None):
        config_path = Path(path) if path else (tmp_repo / ".semver" / "config.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config_dict))
        return str(config_path)
    return _make


@pytest.fixture
def make_version_file(tmp_repo):
    """Write a version file and return its Path."""
    def _make(version="0.1.0", path="VERSION"):
        p = tmp_repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(version + "\n")
        return p
    return _make


@pytest.fixture
def mock_git(monkeypatch):
    """Replace git_semver.git with a mock that records calls.

    Returns (calls_list, mock_fn).  The mock returns a successful result
    by default.  Override per-test by setting mock_fn.side_effect or
    mock_fn.return_value.
    """
    import git_semver

    calls = []
    mock = MagicMock()

    def _git(*args, **kwargs):
        calls.append((args, kwargs))
        result = mock(*args, **kwargs)
        if result is None:
            # Default: successful empty result
            r = MagicMock()
            r.stdout = ""
            r.stderr = ""
            r.returncode = 0
            return r
        return result

    monkeypatch.setattr(git_semver, "git", _git)
    return calls, mock
