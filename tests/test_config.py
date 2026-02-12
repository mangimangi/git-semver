"""Tests for config loading, subdirectory detection, and changelog config."""

import json

import pytest

import git_semver


class TestLoadConfig:
    def test_missing_config_file(self, tmp_repo):
        with pytest.raises(git_semver.SemverError, match="Config not found"):
            git_semver.load_config(str(tmp_repo / "nonexistent.json"))

    def test_valid_root_config(self, make_config):
        path = make_config({"files": ["*.py"], "updates": {"VERSION": "file"}})
        config = git_semver.load_config(path)
        assert config["files"] == ["*.py"]
        assert config["updates"] == {"VERSION": "file"}

    def test_missing_files_key(self, make_config):
        """files key is optional — config loads fine without it."""
        path = make_config({"updates": {"VERSION": "file"}})
        config = git_semver.load_config(path)
        assert config["updates"] == {"VERSION": "file"}

    def test_missing_updates_key(self, make_config):
        """updates key is optional — config loads fine without it."""
        path = make_config({"files": ["*.py"]})
        config = git_semver.load_config(path)
        assert config["files"] == ["*.py"]

    def test_minimal_config(self, make_config):
        """Minimal config with only version_file is valid."""
        path = make_config({"version_file": "VERSION"})
        config = git_semver.load_config(path)
        assert config["version_file"] == "VERSION"

    def test_config_with_subdirectories(self, make_config):
        path = make_config({
            "files": ["*.py"],
            "updates": {"VERSION": "file"},
            "frontend": {
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
        })
        config = git_semver.load_config(path)
        assert "frontend" in config

    def test_subdirectory_only_config(self, make_config):
        """Root files/updates optional when subdirectories are present."""
        path = make_config({
            "frontend": {
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
        })
        config = git_semver.load_config(path)
        assert "frontend" in config

    def test_subdirectory_missing_files(self, make_config):
        """files key is optional in subdirectory configs."""
        path = make_config({
            "frontend": {
                "updates": {"frontend/VERSION": "file"},
            },
        })
        config = git_semver.load_config(path)
        assert "frontend" in config

    def test_subdirectory_missing_updates(self, make_config):
        """updates key is optional in subdirectory configs."""
        path = make_config({
            "frontend": {
                "files": ["frontend/**/*.js"],
            },
        })
        config = git_semver.load_config(path)
        assert "frontend" in config

    def test_multiple_subdirectories(self, make_config):
        path = make_config({
            "frontend": {
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
            "backend": {
                "files": ["backend/**/*.py"],
                "updates": {"backend/VERSION": "file"},
            },
        })
        config = git_semver.load_config(path)
        subdirs = git_semver.get_subdirectories(config)
        assert set(subdirs.keys()) == {"frontend", "backend"}

    def test_root_and_subdirectories(self, make_config):
        path = make_config({
            "version_file": "VERSION",
            "files": ["core/**/*.py"],
            "updates": {"VERSION": "file"},
            "frontend": {
                "files": ["frontend/**/*.js"],
                "updates": {"frontend/VERSION": "file"},
            },
        })
        config = git_semver.load_config(path)
        assert config["files"] == ["core/**/*.py"]
        subdirs = git_semver.get_subdirectories(config)
        assert "frontend" in subdirs


class TestGetSubdirectories:
    def test_empty_config(self):
        config = {"files": [], "updates": {}}
        assert git_semver.get_subdirectories(config) == {}

    def test_only_reserved_keys(self):
        config = {
            "version_file": "VERSION",
            "files": [],
            "updates": {},
            "changelog": True,
            "install": {"on_merge": True},
        }
        assert git_semver.get_subdirectories(config) == {}

    def test_underscore_keys_skipped(self):
        config = {
            "files": [],
            "updates": {},
            "_comment": {"this": "is ignored"},
            "_hidden": {"also": "ignored"},
        }
        assert git_semver.get_subdirectories(config) == {}

    def test_non_dict_values_skipped(self):
        config = {
            "files": [],
            "updates": {},
            "some_string": "not a dict",
            "some_list": [1, 2, 3],
            "some_bool": True,
        }
        assert git_semver.get_subdirectories(config) == {}

    def test_detects_subdirectories(self):
        config = {
            "files": [],
            "updates": {},
            "frontend": {"files": [], "updates": {}},
            "backend": {"files": [], "updates": {}},
        }
        subdirs = git_semver.get_subdirectories(config)
        assert set(subdirs.keys()) == {"frontend", "backend"}

    def test_install_not_detected_as_subdir(self):
        config = {
            "files": [],
            "updates": {},
            "install": {"on_merge": True, "automerge": True},
        }
        assert git_semver.get_subdirectories(config) == {}


class TestGetSubdirConfig:
    def test_existing_subdir(self):
        config = {
            "frontend": {"files": ["*.js"], "updates": {}},
        }
        sub = git_semver.get_subdir_config(config, "frontend")
        assert sub["files"] == ["*.js"]

    def test_nonexistent_subdir(self):
        config = {
            "frontend": {"files": ["*.js"], "updates": {}},
        }
        with pytest.raises(
            git_semver.SemverError,
            match="Subdirectory 'backend' not found",
        ):
            git_semver.get_subdir_config(config, "backend")


class TestGetVersionFile:
    def test_default(self):
        assert git_semver.get_version_file({}) == "VERSION"

    def test_custom(self):
        assert git_semver.get_version_file({"version_file": "ver.txt"}) == "ver.txt"


class TestParseChangelogConfig:
    def test_default_enabled(self):
        config = {"files": [], "updates": {}}
        enabled, f, prefixes = git_semver.parse_changelog_config(config)
        assert enabled is True
        assert f == "CHANGELOG.md"
        assert prefixes == []

    def test_explicit_true(self):
        config = {"files": [], "updates": {}, "changelog": True}
        enabled, f, _ = git_semver.parse_changelog_config(config)
        assert enabled is True
        assert f == "CHANGELOG.md"

    def test_disabled(self):
        config = {"files": [], "updates": {}, "changelog": False}
        enabled, f, _ = git_semver.parse_changelog_config(config)
        assert enabled is False
        assert f is None

    def test_object_form(self):
        config = {
            "files": [], "updates": {},
            "changelog": {
                "file": "CHANGES.md",
                "ignore_prefixes": ["chore:", "docs:"],
            },
        }
        enabled, f, prefixes = git_semver.parse_changelog_config(config)
        assert enabled is True
        assert f == "CHANGES.md"
        assert prefixes == ["chore:", "docs:"]

    def test_object_form_defaults(self):
        config = {"files": [], "updates": {}, "changelog": {}}
        enabled, f, prefixes = git_semver.parse_changelog_config(config)
        assert enabled is True
        assert f == "CHANGELOG.md"
        assert prefixes == []

    def test_subdir_inherits_root_enabled(self):
        config = {
            "changelog": True,
            "frontend": {"files": [], "updates": {}},
        }
        enabled, f, _ = git_semver.parse_changelog_config(config, subdir="frontend")
        assert enabled is True
        assert f == "frontend/CHANGELOG.md"

    def test_subdir_inherits_root_disabled(self):
        config = {
            "changelog": False,
            "frontend": {"files": [], "updates": {}},
        }
        enabled, _, _ = git_semver.parse_changelog_config(config, subdir="frontend")
        assert enabled is False

    def test_subdir_inherits_root_object(self):
        config = {
            "changelog": {
                "file": "CHANGES.md",
                "ignore_prefixes": ["chore:"],
            },
            "frontend": {"files": [], "updates": {}},
        }
        enabled, f, prefixes = git_semver.parse_changelog_config(config, subdir="frontend")
        assert enabled is True
        # Subdir gets its own default path, not root's custom path
        assert f == "frontend/CHANGELOG.md"
        assert prefixes == ["chore:"]

    def test_subdir_own_changelog_config(self):
        config = {
            "changelog": True,
            "frontend": {
                "files": [], "updates": {},
                "changelog": {"file": "frontend/CHANGES.md"},
            },
        }
        enabled, f, _ = git_semver.parse_changelog_config(config, subdir="frontend")
        assert enabled is True
        assert f == "frontend/CHANGES.md"

    def test_subdir_disables_changelog(self):
        config = {
            "changelog": True,
            "frontend": {
                "files": [], "updates": {},
                "changelog": False,
            },
        }
        enabled, _, _ = git_semver.parse_changelog_config(config, subdir="frontend")
        assert enabled is False

    def test_subdir_inherits_default_when_root_unset(self):
        config = {
            "frontend": {"files": [], "updates": {}},
        }
        enabled, f, _ = git_semver.parse_changelog_config(config, subdir="frontend")
        assert enabled is True
        assert f == "frontend/CHANGELOG.md"


class TestVendoredConfigLoading:
    """Tests for v2 vendored config path resolution."""

    def test_vendored_config_preferred_over_default(self, tmp_repo):
        """When vendored config exists, it's used over .semver/config.json."""
        # Create both configs with different content
        default_config = {"files": ["default/**"]}
        vendored_config = {"files": ["vendored/**"]}

        (tmp_repo / ".semver" / "config.json").write_text(json.dumps(default_config))
        vendored_dir = tmp_repo / ".vendored" / "configs"
        vendored_dir.mkdir(parents=True)
        (vendored_dir / "git-semver.json").write_text(json.dumps(vendored_config))

        config = git_semver.load_config()
        assert config["files"] == ["vendored/**"]

    def test_fallback_to_default_when_vendored_missing(self, tmp_repo):
        """Falls back to .semver/config.json when vendored config doesn't exist."""
        default_config = {"files": ["default/**"]}
        (tmp_repo / ".semver" / "config.json").write_text(json.dumps(default_config))

        config = git_semver.load_config()
        assert config["files"] == ["default/**"]

    def test_vendor_key_filtered(self, tmp_repo):
        """The _vendor key is filtered from loaded config."""
        config_data = {
            "files": ["*.py"],
            "_vendor": {"name": "git-semver", "version": "1.0.0"},
        }
        (tmp_repo / ".semver" / "config.json").write_text(json.dumps(config_data))

        config = git_semver.load_config()
        assert "_vendor" not in config
        assert config["files"] == ["*.py"]

    def test_vendor_key_filtered_from_vendored_config(self, tmp_repo):
        """The _vendor key is filtered when loading from vendored path."""
        config_data = {
            "files": ["*.py"],
            "_vendor": {"name": "git-semver", "version": "1.0.0"},
        }
        vendored_dir = tmp_repo / ".vendored" / "configs"
        vendored_dir.mkdir(parents=True)
        (vendored_dir / "git-semver.json").write_text(json.dumps(config_data))

        config = git_semver.load_config()
        assert "_vendor" not in config
        assert config["files"] == ["*.py"]

    def test_explicit_config_flag_overrides_vendored(self, tmp_repo):
        """--config flag skips vendored lookup."""
        vendored_config = {"files": ["vendored/**"]}
        explicit_config = {"files": ["explicit/**"]}

        vendored_dir = tmp_repo / ".vendored" / "configs"
        vendored_dir.mkdir(parents=True)
        (vendored_dir / "git-semver.json").write_text(json.dumps(vendored_config))

        explicit_path = tmp_repo / "custom-config.json"
        explicit_path.write_text(json.dumps(explicit_config))

        config = git_semver.load_config(str(explicit_path))
        assert config["files"] == ["explicit/**"]

    def test_subdirectory_detection_unaffected_by_vendor_key(self, tmp_repo):
        """_vendor key doesn't appear as a subdirectory."""
        config_data = {
            "files": ["*.py"],
            "_vendor": {"name": "git-semver", "version": "1.0.0"},
            "frontend": {"files": ["frontend/**/*.js"]},
        }
        (tmp_repo / ".semver" / "config.json").write_text(json.dumps(config_data))

        config = git_semver.load_config()
        subdirs = git_semver.get_subdirectories(config)
        assert "frontend" in subdirs
        assert "_vendor" not in subdirs

    def test_vendored_config_constant(self):
        """VENDORED_CONFIG constant points to expected path."""
        assert git_semver.VENDORED_CONFIG == ".vendored/configs/git-semver.json"


class TestParseChangelogValue:
    def test_none(self):
        assert git_semver._parse_changelog_value(None) == (True, "CHANGELOG.md", [])

    def test_custom_default_file(self):
        enabled, f, _ = git_semver._parse_changelog_value(True, "custom.md")
        assert f == "custom.md"
