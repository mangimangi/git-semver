"""Tests for file pattern matching."""

import git_semver


class TestMatchesPattern:
    # ── Simple patterns (no /) ──────────────────────────────────────────

    def test_simple_wildcard_match(self):
        assert git_semver.matches_pattern("foo.py", "*.py") is True

    def test_simple_wildcard_no_match(self):
        assert git_semver.matches_pattern("foo.js", "*.py") is False

    def test_simple_wildcard_rejects_nested(self):
        """Single * should not match across /."""
        assert git_semver.matches_pattern("src/foo.py", "*.py") is False

    def test_question_mark(self):
        assert git_semver.matches_pattern("a.py", "?.py") is True

    def test_question_mark_no_match(self):
        assert git_semver.matches_pattern("ab.py", "?.py") is False

    def test_exact_filename(self):
        assert git_semver.matches_pattern("Makefile", "Makefile") is True

    def test_exact_filename_no_match(self):
        assert git_semver.matches_pattern("Makefile", "Dockerfile") is False

    # ── Path-aware patterns (with /) ────────────────────────────────────

    def test_path_pattern_match(self):
        assert git_semver.matches_pattern("src/foo.py", "src/*.py") is True

    def test_path_pattern_wrong_depth(self):
        assert git_semver.matches_pattern("src/sub/foo.py", "src/*.py") is False

    def test_path_pattern_wrong_dir(self):
        assert git_semver.matches_pattern("lib/foo.py", "src/*.py") is False

    def test_path_pattern_exact(self):
        assert git_semver.matches_pattern("src/main.py", "src/main.py") is True

    def test_multi_segment_pattern(self):
        assert git_semver.matches_pattern("a/b/c.py", "a/b/*.py") is True

    def test_multi_segment_mismatch(self):
        assert git_semver.matches_pattern("a/b/c.py", "a/x/*.py") is False

    # ── Double-star patterns ────────────────────────────────────────────

    def test_doublestar_basic(self):
        assert git_semver.matches_pattern("src/foo.py", "src/**/*.py") is True

    def test_doublestar_nested(self):
        assert git_semver.matches_pattern("src/a/b/c/foo.py", "src/**/*.py") is True

    def test_doublestar_wrong_prefix(self):
        assert git_semver.matches_pattern("lib/foo.py", "src/**/*.py") is False

    def test_doublestar_no_suffix(self):
        """Pattern 'src/**' matches anything under src."""
        assert git_semver.matches_pattern("src/anything/here", "src/**") is True

    def test_doublestar_prefix_only(self):
        assert git_semver.matches_pattern("src/deep/file.txt", "src/**") is True

    def test_doublestar_no_prefix(self):
        """Pattern '**/*.py' matches .py files at any depth."""
        assert git_semver.matches_pattern("foo.py", "**/*.py") is True

    def test_doublestar_no_prefix_nested(self):
        assert git_semver.matches_pattern("a/b/c.py", "**/*.py") is True

    def test_doublestar_no_prefix_no_match(self):
        assert git_semver.matches_pattern("foo.js", "**/*.py") is False

    def test_doublestar_match_all(self):
        assert git_semver.matches_pattern("any/path/file.txt", "**") is True

    def test_doublestar_prefix_is_file_itself(self):
        assert git_semver.matches_pattern("src", "src/**") is True

    def test_doublestar_with_yml_suffix(self):
        assert git_semver.matches_pattern(
            "templates/github/workflows/version-bump.yml",
            "templates/github/workflows/*.yml",
        ) is True


class TestCheckFilesChanged:
    def test_matching_files(self):
        changed = ["src/main.py", "README.md"]
        patterns = ["src/**/*.py"]
        matches = git_semver.check_files_changed(changed, patterns)
        assert len(matches) == 1
        assert matches[0] == ("src/main.py", "src/**/*.py")

    def test_no_matches(self):
        changed = ["README.md", "docs/guide.md"]
        patterns = ["src/**/*.py"]
        assert git_semver.check_files_changed(changed, patterns) == []

    def test_multiple_patterns(self):
        changed = ["src/app.py", "lib/util.js"]
        patterns = ["src/**/*.py", "lib/**/*.js"]
        matches = git_semver.check_files_changed(changed, patterns)
        assert len(matches) == 2

    def test_one_match_per_file(self):
        """A file matching multiple patterns should only appear once."""
        changed = ["src/main.py"]
        patterns = ["src/**/*.py", "**/*.py"]
        matches = git_semver.check_files_changed(changed, patterns)
        assert len(matches) == 1

    def test_empty_changed(self):
        assert git_semver.check_files_changed([], ["*.py"]) == []

    def test_empty_patterns(self):
        assert git_semver.check_files_changed(["foo.py"], []) == []
