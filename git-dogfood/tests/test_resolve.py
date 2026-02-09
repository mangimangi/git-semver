"""Tests for the dogfood/resolve script."""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ── Import resolve script as module ────────────────────────────────────────

ROOT = Path(__file__).parent.parent


def _import_resolve():
    filepath = str(ROOT / "dogfood" / "resolve")
    loader = importlib.machinery.SourceFileLoader("dogfood_resolve", filepath)
    spec = importlib.util.spec_from_loader("dogfood_resolve", loader, origin=filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules["dogfood_resolve"] = module
    spec.loader.exec_module(module)
    return module


resolve = _import_resolve()


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".vendored").mkdir()
    return tmp_path


@pytest.fixture
def make_config(tmp_repo):
    def _make(config_dict):
        path = tmp_repo / ".vendored" / "config.json"
        path.write_text(json.dumps(config_dict, indent=2) + "\n")
        return str(path)
    return _make


# ── Tests: find_dogfood_vendor ─────────────────────────────────────────────

class TestFindDogfoodVendor:
    def test_finds_dogfood_vendor(self):
        config = {
            "vendors": {
                "git-vendored": {"repo": "o/gv"},
                "git-semver": {"repo": "o/gs", "dogfood": True},
                "pearls": {"repo": "o/p"},
            }
        }
        assert resolve.find_dogfood_vendor(config) == "git-semver"

    def test_returns_none_when_no_dogfood(self):
        config = {
            "vendors": {
                "git-vendored": {"repo": "o/gv"},
                "pearls": {"repo": "o/p"},
            }
        }
        assert resolve.find_dogfood_vendor(config) is None

    def test_returns_none_when_dogfood_false(self):
        config = {
            "vendors": {
                "git-semver": {"repo": "o/gs", "dogfood": False},
            }
        }
        assert resolve.find_dogfood_vendor(config) is None

    def test_empty_vendors(self):
        assert resolve.find_dogfood_vendor({"vendors": {}}) is None

    def test_no_vendors_key(self):
        assert resolve.find_dogfood_vendor({}) is None

    def test_first_dogfood_wins(self):
        config = {
            "vendors": {
                "a": {"repo": "o/a", "dogfood": True},
                "b": {"repo": "o/b", "dogfood": True},
            }
        }
        # Should return first one found
        result = resolve.find_dogfood_vendor(config)
        assert result in ("a", "b")


# ── Tests: load_vendor_config ──────────────────────────────────────────────

class TestLoadVendorConfig:
    def test_loads_config(self, make_config):
        make_config({"vendors": {"x": {"repo": "o/x"}}})
        config = resolve.load_vendor_config()
        assert "vendors" in config

    def test_missing_file_returns_none(self, tmp_repo):
        assert resolve.load_vendor_config("/nonexistent/config.json") is None


# ── Tests: main ────────────────────────────────────────────────────────────

class TestMain:
    def test_outputs_vendor(self, make_config, capsys):
        make_config({"vendors": {"git-semver": {"repo": "o/gs", "dogfood": True}}})
        resolve.main()
        out = capsys.readouterr().out
        assert "vendor=git-semver" in out

    def test_no_dogfood_no_output(self, make_config, capsys):
        make_config({"vendors": {"pearls": {"repo": "o/p"}}})
        resolve.main()
        out = capsys.readouterr().out
        assert "vendor=" not in out

    def test_no_config_no_crash(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        resolve.main()
        out = capsys.readouterr().out
        assert "vendor=" not in out
