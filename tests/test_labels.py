"""Tests for git-deps.labels.json: reading, checking and writing labels."""

import json
import re
from pathlib import Path

import pytest

import git_semver

ROOT = Path(__file__).parent.parent
SHA = "455ee13c1f0e5d8b7a2f3e9c6d4b1a0f8e7d6c5b"
SHA2 = "0123456789abcdef0123456789abcdef01234567"


def readme_example():
    """The labels file example in README.md's "Labels" section."""
    readme = (ROOT / "README.md").read_text()
    section = readme[readme.index("### Labels (`git-deps.labels.json`)"):]
    match = re.search(r"```json\n(.*?)```", section, re.S)
    return match.group(1)


def label(**fields):
    base = {"name": "defect", "reason": "broken", "date": "2026-11-28",
            "commit": SHA}
    base.update(fields)
    return {k: v for k, v in base.items() if v is not None}


def file_text(versions, **extra):
    data = {"format": 1, "versions": versions}
    data.update(extra)
    return json.dumps(data)


# ── Reading ─────────────────────────────────────────────────────────────────

class TestLoad:
    def test_missing_file_reads_empty(self, tmp_repo):
        assert git_semver.load_labels() == {"format": 1, "versions": {}}
        assert git_semver.load_labels(tmp_repo / "nope.json") == git_semver.empty_labels()

    def test_default_path_is_repo_root_file(self):
        assert git_semver.LABELS_FILE == "git-deps.labels.json"

    def test_reads_file(self, tmp_repo):
        (tmp_repo / git_semver.LABELS_FILE).write_text(
            file_text({"v0.1.2": [label()]}))
        data = git_semver.load_labels()
        assert data["versions"]["v0.1.2"][0]["commit"] == SHA

    def test_readme_example_is_valid(self):
        data = git_semver.parse_labels(readme_example())
        assert set(data["versions"]) == {"v0.1.2", "backend/v2.3.0"}

    def test_reason_and_fixed_in_optional(self):
        git_semver.parse_labels(file_text({"v1.0.0": [label(reason=None)]}))

    def test_empty_label_list_ok(self):
        git_semver.parse_labels(file_text({"v1.0.0": []}))


class TestTolerantContent:
    def test_unknown_name_extra_field_extra_key_kept(self, tmp_repo):
        lb = label(name="eol", runtime="python3.10")
        text = file_text({"v1.0.0": [lb]}, publisher="someone")
        path = tmp_repo / git_semver.LABELS_FILE
        path.write_text(text)
        data = git_semver.load_labels(path)
        git_semver.save_labels(path, data)
        back = json.loads(path.read_text())
        assert back["publisher"] == "someone"
        assert back["versions"]["v1.0.0"][0]["name"] == "eol"
        assert back["versions"]["v1.0.0"][0]["runtime"] == "python3.10"

    def test_unknown_fields_after_known_in_read_order(self):
        lb = {"zeta": 1, "commit": SHA, "alpha": 2, "name": "defect",
              "date": "2026-11-28"}
        data = git_semver.parse_labels(file_text({"v1.0.0": [lb]}))
        out = json.loads(git_semver.dump_labels(data))
        assert list(out["versions"]["v1.0.0"][0]) == [
            "name", "date", "commit", "zeta", "alpha"]

    def test_top_level_order(self):
        text = json.dumps({"z": 1, "versions": {}, "a": 2, "format": 1})
        out = json.loads(git_semver.dump_labels(git_semver.parse_labels(text)))
        assert list(out) == ["format", "versions", "z", "a"]


class TestStrictStructure:
    @pytest.mark.parametrize("text, message", [
        ("{not json", "invalid JSON"),
        ("[]", "top level must be an object"),
        ('{"versions": {}}', "'format' is missing"),
        ('{"format": "1", "versions": {}}', "'format' must be an integer"),
        ('{"format": true, "versions": {}}', "'format' must be an integer"),
        ('{"format": 2, "versions": {}}',
         r"format 2 is not supported \(this git-semver reads format 1\)"),
        ('{"format": 0, "versions": {}}', "format 0 is not supported"),
        ('{"format": 1}', "'versions' is missing"),
        ('{"format": 1, "versions": []}', "'versions' must be an object"),
        ('{"format": 1, "versions": {"1.0.0": []}}',
         r"versions\['1.0.0'\]: not a version tag"),
        ('{"format": 1, "versions": {"latest": []}}', "not a version tag"),
        ('{"format": 1, "versions": {"v1.0.0\\n": []}}', "not a version tag"),
        ('{"format": 1, "versions": {"v1.0.0": {}}}',
         r"versions\['v1.0.0'\]: must be a list of labels"),
        ('{"format": 1, "versions": {"v1.0.0": ["defect"]}}',
         r"versions\['v1.0.0'\]\[0\]: a label must be an object"),
    ])
    def test_refused(self, text, message):
        with pytest.raises(git_semver.SemverError, match=message):
            git_semver.parse_labels(text)

    @pytest.mark.parametrize("fields, message", [
        ({"name": None}, "'name' must be a non-empty string"),
        ({"name": ""}, "'name' must be a non-empty string"),
        ({"name": 3}, "'name' must be a non-empty string"),
        ({"commit": None}, "'commit' must be a 40-hex commit sha"),
        ({"commit": "abc123"}, "'commit' must be a 40-hex commit sha"),
        ({"commit": SHA.upper()}, "'commit' must be a 40-hex commit sha"),
        ({"date": None}, "'date' must be a YYYY-MM-DD date"),
        ({"date": "28/11/2026"}, "'date' must be a YYYY-MM-DD date"),
        ({"date": "2026-13-40"}, "'date' must be a YYYY-MM-DD date"),
        ({"date": 20261128}, "'date' must be a YYYY-MM-DD date"),
        ({"reason": 5}, "'reason' must be a one-line string"),
        ({"reason": "two\nlines"}, "'reason' must be a one-line string"),
        ({"reason": "cr\rhere"}, "'reason' must be a one-line string"),
        ({"fixed_in": "v0.1.3"}, "'fixed_in' must be an X.Y.Z version"),
        ({"fixed_in": "0.1"}, "'fixed_in' must be an X.Y.Z version"),
        ({"fixed_in": 13}, "'fixed_in' must be an X.Y.Z version"),
    ])
    def test_bad_label_refused_with_location(self, fields, message):
        text = file_text({"v1.0.0": [label(), label(**fields)]})
        with pytest.raises(git_semver.SemverError,
                           match=r"versions\['v1.0.0'\]\[1\]: " + message):
            git_semver.parse_labels(text)

    def test_message_names_file(self, tmp_repo):
        path = tmp_repo / "x.json"
        path.write_text("[]")
        with pytest.raises(git_semver.SemverError, match="x.json: the top level"):
            git_semver.load_labels(path)


# ── Writing ─────────────────────────────────────────────────────────────────

class TestWrite:
    def test_readme_example_round_trips_byte_identical(self, tmp_repo):
        text = readme_example()
        path = tmp_repo / git_semver.LABELS_FILE
        path.write_text(text)
        git_semver.save_labels(path, git_semver.load_labels(path))
        assert path.read_text() == text

    def test_empty_file_form(self):
        assert git_semver.dump_labels(git_semver.empty_labels()) == (
            '{\n  "format": 1,\n  "versions": {}\n}\n')

    def test_versions_sorted_by_component_then_precedence(self):
        versions = {t: [label()] for t in [
            "backend/v1.0.0", "v0.10.0", "api/v2.0.0", "v0.9.0",
            "backend/v0.2.0", "v1.0.0"]}
        out = json.loads(git_semver.dump_labels(
            git_semver.parse_labels(file_text(versions))))
        assert list(out["versions"]) == [
            "v0.9.0", "v0.10.0", "v1.0.0",
            "api/v2.0.0", "backend/v0.2.0", "backend/v1.0.0"]

    def test_labels_sorted_by_name_fields_ordered(self):
        lbs = [{"fixed_in": "1.0.1", "commit": SHA, "date": "2026-11-28",
                "reason": "r", "name": "zz"},
               label(name="defect")]
        out = json.loads(git_semver.dump_labels(
            git_semver.parse_labels(file_text({"v1.0.0": lbs}))))
        got = out["versions"]["v1.0.0"]
        assert [lb["name"] for lb in got] == ["defect", "zz"]
        assert list(got[1]) == ["name", "reason", "date", "commit", "fixed_in"]

    def test_non_ascii_kept_and_trailing_newline(self):
        data = git_semver.parse_labels(
            file_text({"v1.0.0": [label(reason="café broke")]}))
        text = git_semver.dump_labels(data)
        assert "café broke" in text
        assert text.endswith("}\n")
        assert '\n  "versions"' in text

    def test_save_does_not_change_input(self, tmp_repo):
        data = git_semver.parse_labels(file_text(
            {"v2.0.0": [label()], "v1.0.0": [label()]}))
        git_semver.save_labels(tmp_repo / "f.json", data)
        assert list(data["versions"]) == ["v2.0.0", "v1.0.0"]


class TestVersionTags:
    def test_split_root_and_subdir(self):
        assert git_semver.split_version_tag("v1.2.3") == (None, (1, 2, 3))
        assert git_semver.split_version_tag("a/b/v0.1.0") == ("a/b", (0, 1, 0))

    @pytest.mark.parametrize("tag", ["latest", "1.2.3", "v1.2", None, "v1.2.3\n"])
    def test_split_refuses_non_version_tags(self, tag):
        with pytest.raises(git_semver.SemverError, match="not a version tag"):
            git_semver.split_version_tag(tag)

    def test_schema_listed_in_files(self):
        config = json.loads(
            (ROOT / ".vendored/configs/git-semver.json").read_text())
        assert "templates/labels.schema" in config["files"]
        schema = json.loads((ROOT / "templates/labels.schema").read_text())
        assert schema["properties"]["format"]["const"] == 1
