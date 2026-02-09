"""Tests for file update operations."""

from pathlib import Path

import git_semver


class TestApplyUpdates:
    def test_file_action(self, tmp_repo):
        (tmp_repo / "VERSION").write_text("0.1.0\n")
        git_semver.apply_updates({"VERSION": "file"}, "0.2.0")
        assert (tmp_repo / "VERSION").read_text() == "0.2.0\n"

    def test_pattern_without_equals(self, tmp_repo):
        (tmp_repo / "setup.py").write_text('version="0.1.0"\n')
        git_semver.apply_updates({"setup.py": ['version="']}, "0.2.0")
        assert (tmp_repo / "setup.py").read_text() == 'version="0.2.0"\n'

    def test_pattern_with_equals(self, tmp_repo):
        (tmp_repo / "src.py").write_text('VERSION = "0.1.0"\n')
        git_semver.apply_updates({"src.py": ["VERSION = "]}, "0.2.0")
        assert (tmp_repo / "src.py").read_text() == 'VERSION = "0.2.0"\n'

    def test_pattern_preserves_single_quotes(self, tmp_repo):
        (tmp_repo / "src.py").write_text("VERSION = '0.1.0'\n")
        git_semver.apply_updates({"src.py": ["VERSION = "]}, "0.2.0")
        assert (tmp_repo / "src.py").read_text() == "VERSION = '0.2.0'\n"

    def test_pattern_no_quotes(self, tmp_repo):
        """Pattern with = but value without quotes."""
        (tmp_repo / "src.py").write_text("VERSION = 0.1.0\n")
        git_semver.apply_updates({"src.py": ["VERSION = "]}, "0.2.0")
        assert (tmp_repo / "src.py").read_text() == "VERSION = 0.2.0\n"

    def test_multiple_patterns_same_file(self, tmp_repo):
        content = 'VERSION = "0.1.0"\nAPI_VERSION = "0.1.0"\n'
        (tmp_repo / "src.py").write_text(content)
        git_semver.apply_updates(
            {"src.py": ["VERSION = ", "API_VERSION = "]}, "0.2.0"
        )
        result = (tmp_repo / "src.py").read_text()
        assert 'VERSION = "0.2.0"' in result
        assert 'API_VERSION = "0.2.0"' in result

    def test_missing_file_skipped(self, tmp_repo, capsys):
        git_semver.apply_updates({"nonexistent.txt": "file"}, "0.2.0")
        captured = capsys.readouterr()
        assert "not found, skipping" in captured.out

    def test_multiple_files(self, tmp_repo):
        (tmp_repo / "VERSION").write_text("0.1.0\n")
        (tmp_repo / "lib.py").write_text("v0.1.0\n")
        git_semver.apply_updates(
            {"VERSION": "file", "lib.py": ["v"]},
            "0.2.0",
        )
        assert (tmp_repo / "VERSION").read_text() == "0.2.0\n"
        assert (tmp_repo / "lib.py").read_text() == "v0.2.0\n"

    def test_subdirectory_file_paths(self, tmp_repo):
        """Updates work with paths inside subdirectories."""
        (tmp_repo / "frontend").mkdir()
        (tmp_repo / "frontend" / "VERSION").write_text("1.0.0\n")
        git_semver.apply_updates({"frontend/VERSION": "file"}, "1.0.1")
        assert (tmp_repo / "frontend" / "VERSION").read_text() == "1.0.1\n"
