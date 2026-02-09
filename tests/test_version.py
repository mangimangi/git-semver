"""Tests for version parsing, computation, and formatting."""

import pytest

import git_semver


class TestParseVersion:
    def test_valid_version(self):
        assert git_semver.parse_version("1.2.3") == (1, 2, 3)

    def test_zero_version(self):
        assert git_semver.parse_version("0.0.0") == (0, 0, 0)

    def test_large_numbers(self):
        assert git_semver.parse_version("100.200.300") == (100, 200, 300)

    def test_too_few_parts(self):
        with pytest.raises(git_semver.SemverError, match="Invalid version format"):
            git_semver.parse_version("1.2")

    def test_too_many_parts(self):
        with pytest.raises(git_semver.SemverError, match="Invalid version format"):
            git_semver.parse_version("1.2.3.4")

    def test_single_number(self):
        with pytest.raises(git_semver.SemverError, match="Invalid version format"):
            git_semver.parse_version("1")

    def test_non_numeric(self):
        with pytest.raises(git_semver.SemverError, match="Invalid version format"):
            git_semver.parse_version("a.b.c")

    def test_mixed_non_numeric(self):
        with pytest.raises(git_semver.SemverError, match="Invalid version format"):
            git_semver.parse_version("1.2.beta")

    def test_empty_string(self):
        with pytest.raises(git_semver.SemverError, match="Invalid version format"):
            git_semver.parse_version("")


class TestComputeNewVersion:
    def test_patch_bump(self):
        assert git_semver.compute_new_version(1, 2, 3, "patch") == (1, 2, 4)

    def test_minor_bump(self):
        assert git_semver.compute_new_version(1, 2, 3, "minor") == (1, 3, 0)

    def test_major_bump(self):
        assert git_semver.compute_new_version(1, 2, 3, "major") == (2, 0, 0)

    def test_patch_from_zero(self):
        assert git_semver.compute_new_version(0, 0, 0, "patch") == (0, 0, 1)

    def test_minor_resets_patch(self):
        assert git_semver.compute_new_version(1, 2, 5, "minor") == (1, 3, 0)

    def test_major_resets_minor_and_patch(self):
        assert git_semver.compute_new_version(1, 5, 9, "major") == (2, 0, 0)


class TestFormatVersion:
    def test_basic(self):
        assert git_semver.format_version(1, 2, 3) == "1.2.3"

    def test_zeros(self):
        assert git_semver.format_version(0, 0, 0) == "0.0.0"

    def test_large(self):
        assert git_semver.format_version(10, 20, 30) == "10.20.30"


class TestReadVersion:
    def test_reads_from_file(self, make_version_file):
        make_version_file("1.2.3")
        assert git_semver.read_version("VERSION") == "1.2.3"

    def test_strips_trailing_newline(self, make_version_file):
        make_version_file("1.2.3")
        assert git_semver.read_version("VERSION") == "1.2.3"

    def test_strips_whitespace(self, tmp_repo):
        (tmp_repo / "VERSION").write_text("  1.2.3  \n")
        assert git_semver.read_version("VERSION") == "1.2.3"

    def test_missing_file(self, tmp_repo):
        with pytest.raises(git_semver.SemverError, match="Version file not found"):
            git_semver.read_version("NONEXISTENT")
