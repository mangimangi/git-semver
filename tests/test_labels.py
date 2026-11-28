"""Tests for git-deps.labels.json: reading, checking and writing labels."""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
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


# ── label / unlabel / labels (real local repositories) ──────────────────────


def g(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repository with v0.1.2, v0.1.3, v0.2.0 and backend/v1.0.0 tagged,
    run from a subdirectory to show the file goes to the root."""
    g(tmp_path, "init", "-q", "-b", "main")
    shas = {}
    for tag in ["v0.1.2", "v0.1.3", "backend/v1.0.0", "backend/v1.1.0", "v0.2.0"]:
        g(tmp_path, "commit", "-q", "--allow-empty", "-m", tag)
        g(tmp_path, "tag", "-a", tag, "-m", tag)
        shas[tag] = g(tmp_path, "rev-parse", "HEAD")
    g(tmp_path, "commit", "-q", "--allow-empty", "-m", "untagged")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    return tmp_path, shas


def cli(monkeypatch, *argv):
    """Run git-semver's main() with argv; returns the exit code."""
    monkeypatch.setattr(sys, "argv", ["git-semver", *argv])
    try:
        git_semver.main()
    except SystemExit as e:
        return e.code
    return 0


def state(root):
    return (g(root, "log", "--all", "--format=%H"), g(root, "tag", "-l"),
            g(root, "status", "--porcelain", "--untracked-files=no"))


def read_file(root):
    return json.loads((root / git_semver.LABELS_FILE).read_text())


class TestLabelCommand:
    def test_labels_tagged_version(self, repo, monkeypatch, capsys):
        root, shas = repo
        before = state(root)
        assert cli(monkeypatch, "label", "0.1.2", "defect",
                   "--reason", "init fails") == 0
        out = capsys.readouterr().out
        assert "Labelled v0.1.2 defect" in out
        assert "pull request" in out
        assert read_file(root) == {"format": 1, "versions": {"v0.1.2": [{
            "name": "defect", "reason": "init fails", "date": today(),
            "commit": shas["v0.1.2"]}]}}
        # No commit, tag or push; only the untracked file appears.
        assert state(root) == before

    def test_v_prefix_and_fixed_in(self, repo, monkeypatch):
        root, shas = repo
        assert cli(monkeypatch, "label", "v0.1.2", "defect", "--reason", "r",
                   "--fixed-in", "v0.1.3") == 0
        assert read_file(root)["versions"]["v0.1.2"][0]["fixed_in"] == "0.1.3"

    def test_subdir(self, repo, monkeypatch):
        root, shas = repo
        assert cli(monkeypatch, "label", "1.0.0", "defect", "--reason", "r",
                   "--fixed-in", "1.1.0", "--subdir", "backend") == 0
        lb = read_file(root)["versions"]["backend/v1.0.0"][0]
        assert lb["commit"] == shas["backend/v1.0.0"]
        assert lb["fixed_in"] == "1.1.0"

    @pytest.mark.parametrize("argv, message", [
        (["9.9.9", "defect", "--reason", "r"], "no tag v9.9.9: only a released"),
        (["1.0.0", "defect", "--reason", "r"], "no tag v1.0.0"),
        (["0.1.2", "defect"], "needs --reason"),
        (["0.1.2", "defect", "--reason", "  "], "needs --reason"),
        (["0.1.2", "defect", "--reason", "a\nb"], "--reason must be one line"),
        (["0.1.2", "eol", "--reason", "r"], "makes only the 'defect' label, not 'eol'"),
        (["0.1.2", "defect", "--reason", "r", "--fixed-in", "0.1.9"],
         "--fixed-in 0.1.9: no tag v0.1.9"),
        (["0.1.3", "defect", "--reason", "r", "--fixed-in", "0.1.3"],
         "--fixed-in 0.1.3 is not higher than the labelled 0.1.3"),
        (["0.1.3", "defect", "--reason", "r", "--fixed-in", "0.1.2"],
         "is not higher"),
        (["0.1.2", "defect", "--reason", "r", "--fixed-in", "1.0.0"],
         "no tag v1.0.0"),
        (["not-a-version", "defect", "--reason", "r"], "Invalid version format"),
    ])
    def test_refused(self, repo, monkeypatch, capsys, argv, message):
        root, _ = repo
        assert cli(monkeypatch, "label", *argv) == 1
        assert message in capsys.readouterr().err
        assert not (root / git_semver.LABELS_FILE).exists()

    def test_relabel_updates_without_duplicating(self, repo, monkeypatch, capsys):
        root, shas = repo
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "first",
            "--fixed-in", "0.1.3")
        data = read_file(root)
        data["versions"]["v0.1.2"][0]["date"] = "2026-01-01"
        data["versions"]["v0.1.2"][0]["extra"] = "kept"
        (root / git_semver.LABELS_FILE).write_text(json.dumps(data))
        capsys.readouterr()
        assert cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "second") == 0
        assert "Updated defect on v0.1.2" in capsys.readouterr().out
        labels = read_file(root)["versions"]["v0.1.2"]
        assert labels == [{"name": "defect", "reason": "second",
                           "date": "2026-01-01", "commit": shas["v0.1.2"],
                           "fixed_in": "0.1.3", "extra": "kept"}]
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "third",
            "--fixed-in", "0.2.0")
        assert read_file(root)["versions"]["v0.1.2"][0]["fixed_in"] == "0.2.0"

    def test_malformed_file_refused(self, repo, monkeypatch, capsys):
        root, _ = repo
        (root / git_semver.LABELS_FILE).write_text('{"format": 2, "versions": {}}')
        assert cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "r") == 1
        assert "format 2 is not supported" in capsys.readouterr().err


class TestUnlabelCommand:
    def test_restores_pre_existing_file_byte_identically(self, repo, monkeypatch, capsys):
        root, shas = repo
        lb = label(name="eol", commit=shas["v0.1.3"], vendor_note="x")
        text = git_semver.dump_labels(git_semver.parse_labels(
            file_text({"v0.1.3": [lb]}, publisher="p")))
        path = root / git_semver.LABELS_FILE
        path.write_text(text)
        cli(monkeypatch, "label", "0.1.3", "defect", "--reason", "r")
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "r")
        assert cli(monkeypatch, "unlabel", "0.1.2", "defect") == 0
        assert cli(monkeypatch, "unlabel", "v0.1.3", "defect") == 0
        assert "Removed defect from v0.1.3" in capsys.readouterr().out
        assert path.read_text() == text

    def test_deletes_file_label_created(self, repo, monkeypatch):
        root, _ = repo
        before = state(root)
        cli(monkeypatch, "label", "1.0.0", "defect", "--reason", "r",
            "--subdir", "backend")
        assert cli(monkeypatch, "unlabel", "1.0.0", "defect",
                   "--subdir", "backend") == 0
        assert not (root / git_semver.LABELS_FILE).exists()
        assert state(root) == before

    def test_keeps_file_with_unknown_top_level_key(self, repo, monkeypatch):
        root, _ = repo
        path = root / git_semver.LABELS_FILE
        path.write_text(file_text({}, publisher="p"))
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "r")
        cli(monkeypatch, "unlabel", "0.1.2", "defect")
        assert json.loads(path.read_text()) == {
            "format": 1, "versions": {}, "publisher": "p"}

    def test_missing_label_says_so_exit_0(self, repo, monkeypatch, capsys):
        root, _ = repo
        assert cli(monkeypatch, "unlabel", "0.1.2", "defect") == 0
        assert "No defect label on v0.1.2" in capsys.readouterr().out
        assert not (root / git_semver.LABELS_FILE).exists()
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "r")
        assert cli(monkeypatch, "unlabel", "0.1.2", "eol") == 0
        assert "No eol label on v0.1.2" in capsys.readouterr().out

    def test_unknown_name_untagged_version(self, repo, monkeypatch):
        root, shas = repo
        path = root / git_semver.LABELS_FILE
        path.write_text(file_text({"v5.0.0": [label(name="eol")],
                                   "v0.1.2": [label(name="eol")]}))
        assert cli(monkeypatch, "unlabel", "5.0.0", "eol") == 0
        assert list(read_file(root)["versions"]) == ["v0.1.2"]


class TestLabelsCommand:
    @pytest.fixture
    def labelled(self, repo, monkeypatch, capsys):
        root, shas = repo
        cli(monkeypatch, "label", "0.1.3", "defect", "--reason", "late",
            "--fixed-in", "0.2.0")
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "early")
        cli(monkeypatch, "label", "1.0.0", "defect", "--reason", "api",
            "--subdir", "backend")
        data = read_file(root)
        data["versions"]["v0.1.2"].append(
            {"name": "eol", "date": "2026-01-01", "commit": shas["v0.1.2"]})
        (root / git_semver.LABELS_FILE).write_text(json.dumps(data))
        capsys.readouterr()
        return root, shas

    def test_human_all(self, labelled, monkeypatch, capsys):
        root, shas = labelled
        assert cli(monkeypatch, "labels") == 0
        d = today()
        assert capsys.readouterr().out.splitlines() == [
            f"v0.1.2  defect  {d}  {shas['v0.1.2'][:7]}  — early",
            f"v0.1.2  eol  2026-01-01  {shas['v0.1.2'][:7]}",
            f"v0.1.3  defect  {d}  {shas['v0.1.3'][:7]}  fixed in 0.2.0  — late",
            f"backend/v1.0.0  defect  {d}  {shas['backend/v1.0.0'][:7]}  — api",
        ]

    def test_filter_version(self, labelled, monkeypatch, capsys):
        assert cli(monkeypatch, "labels", "v0.1.3") == 0
        out = capsys.readouterr().out.splitlines()
        assert len(out) == 1 and out[0].startswith("v0.1.3  defect")
        assert cli(monkeypatch, "labels", "1.0.0", "--subdir", "backend") == 0
        assert capsys.readouterr().out.startswith("backend/v1.0.0  defect")

    def test_filter_component(self, labelled, monkeypatch, capsys):
        assert cli(monkeypatch, "labels", "--subdir", "backend") == 0
        out = capsys.readouterr().out.splitlines()
        assert [line.split()[0] for line in out] == ["backend/v1.0.0"]

    def test_json(self, labelled, monkeypatch, capsys):
        root, _ = labelled
        assert cli(monkeypatch, "labels", "--json") == 0
        out = capsys.readouterr().out
        assert out == git_semver.dump_labels(git_semver.load_labels(
            root / git_semver.LABELS_FILE))
        assert cli(monkeypatch, "labels", "0.1.3", "--json") == 0
        assert list(json.loads(capsys.readouterr().out)["versions"]) == ["v0.1.3"]

    def test_nothing_when_empty(self, repo, monkeypatch, capsys):
        assert cli(monkeypatch, "labels") == 0
        assert cli(monkeypatch, "labels", "0.1.2") == 0
        assert capsys.readouterr().out == ""

    def test_malformed_file_is_error(self, repo, monkeypatch, capsys):
        root, _ = repo
        (root / git_semver.LABELS_FILE).write_text("[]")
        assert cli(monkeypatch, "labels") == 1
        assert "the top level must be an object" in capsys.readouterr().err

    def test_no_command_commits_tags_or_pushes(self, labelled, monkeypatch):
        root, _ = labelled
        before = state(root)
        cli(monkeypatch, "labels", "--json")
        cli(monkeypatch, "unlabel", "0.1.2", "eol")
        cli(monkeypatch, "label", "0.1.2", "defect", "--reason", "again")
        assert state(root) == before
