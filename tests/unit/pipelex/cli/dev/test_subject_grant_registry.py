"""Unit tests for the subject-grants registry: loading/validation, symmetric staleness (dead grants), file order."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    SubjectGrant,
    SubjectGrantRegistryError,
    ViolationKind,
    collect_all_violations,
    find_unsorted_grants,
    load_subject_grants,
)

_VALID_REGISTRY = """\
version = 1

["pipelex/sample/module.py::render"]
param = "node"
rationale = "Verb-object; single operand."

["pipelex/sample/module.py::Builder.build"]
param = "spec"
rationale = "Factory from source: builds from the spec."
"""

#: The same two entries in the order the writer emits them.
_SORTED_REGISTRY = """\
version = 1

["pipelex/sample/module.py::Builder.build"]
param = "spec"
rationale = "Factory from source: builds from the spec."

["pipelex/sample/module.py::render"]
param = "node"
rationale = "Verb-object; single operand."
"""

#: A multi-line rationale whose body carries a line that LOOKS like a table header — valid TOML the
#: text scan would read as one entry more than the parser found.
_PHANTOM_HEADER_REGISTRY = '''\
version = 1

["pipelex/sample/module.py::render"]
param = "node"
rationale = """Verb-object.
["pipelex/sample/module.py::ghost"]
"""
'''


def _write_registry(root: Path, *, content: str) -> None:
    (root / "subject_grants.toml").write_text(content, encoding="utf-8")


class TestSubjectGrantRegistry:
    def test_valid_registry_loads(self, tmp_path: Path) -> None:
        """A well-formed registry round-trips into typed grants."""
        _write_registry(tmp_path, content=_VALID_REGISTRY)
        grants = load_subject_grants(root=tmp_path)
        assert grants == {
            "pipelex/sample/module.py::render": SubjectGrant(param="node", rationale="Verb-object; single operand."),
            "pipelex/sample/module.py::Builder.build": SubjectGrant(param="spec", rationale="Factory from source: builds from the spec."),
        }

    def test_missing_registry_is_an_explicit_error(self, tmp_path: Path) -> None:
        """No file means no verdict — never a silent empty registry (that would mass-flag every grant)."""
        with pytest.raises(SubjectGrantRegistryError, match="not found"):
            load_subject_grants(root=tmp_path)

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content="version = [broken\n")
        with pytest.raises(SubjectGrantRegistryError, match="not valid TOML"):
            load_subject_grants(root=tmp_path)

    def test_missing_version_raises(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content='["pipelex/a.py::f"]\nparam = "x"\nrationale = "y"\n')
        with pytest.raises(SubjectGrantRegistryError, match="version = 1"):
            load_subject_grants(root=tmp_path)

    def test_wrong_version_raises(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content="version = 2\n")
        with pytest.raises(SubjectGrantRegistryError, match="version = 1"):
            load_subject_grants(root=tmp_path)

    def test_malformed_key_raises(self, tmp_path: Path) -> None:
        """An entry key must be '<relative_path>::<qualified_name>' — typos fail the check, they don't rot."""
        _write_registry(tmp_path, content='version = 1\n["pipelex/a.py"]\nparam = "x"\nrationale = "y"\n')
        with pytest.raises(SubjectGrantRegistryError, match="not of the form"):
            load_subject_grants(root=tmp_path)

    def test_unknown_entry_key_raises(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content='version = 1\n["pipelex/a.py::f"]\nparam = "x"\nrationale = "y"\nreviewer = "me"\n')
        with pytest.raises(SubjectGrantRegistryError, match="unknown key"):
            load_subject_grants(root=tmp_path)

    def test_empty_param_raises(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content='version = 1\n["pipelex/a.py::f"]\nparam = ""\nrationale = "y"\n')
        with pytest.raises(SubjectGrantRegistryError, match="non-empty string `param`"):
            load_subject_grants(root=tmp_path)

    def test_blank_rationale_raises(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content='version = 1\n["pipelex/a.py::f"]\nparam = "x"\nrationale = "   "\n')
        with pytest.raises(SubjectGrantRegistryError, match="non-empty `rationale`"):
            load_subject_grants(root=tmp_path)

    def test_transitional_seeded_key_rejected(self, tmp_path: Path) -> None:
        """The transitional `seeded` field is gone from the schema — any surviving entry fails the load."""
        _write_registry(tmp_path, content='version = 1\n["pipelex/a.py::f"]\nparam = "x"\nrationale = "y"\nseeded = true\n')
        with pytest.raises(SubjectGrantRegistryError, match="unknown key"):
            load_subject_grants(root=tmp_path)

    def test_dead_grant_for_deleted_def_flagged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A grant whose def no longer exists is a violation — staleness is symmetric (D7)."""
        source_root = tmp_path / "pipelex" / "sample"
        source_root.mkdir(parents=True)
        (source_root / "module.py").write_text("def render(node):\n    return node\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        grants = {
            "pipelex/sample/module.py::render": SubjectGrant(param="node", rationale="ok"),
            "pipelex/sample/module.py::ghost": SubjectGrant(param="spec", rationale="def was deleted"),
        }
        violations = collect_all_violations(Path("pipelex"), grants=grants)
        assert [violation.kind for violation in violations] == [ViolationKind.DEAD_GRANT]
        assert violations[0].qualified_name == "ghost"
        assert violations[0].lineno == 0

    def test_dead_grant_for_demoted_def_flagged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A grant whose def went fully keyword-only is dead too — the entry must be cleaned up."""
        source_root = tmp_path / "pipelex" / "sample"
        source_root.mkdir(parents=True)
        (source_root / "module.py").write_text("def render(*, node):\n    return node\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        grants = {"pipelex/sample/module.py::render": SubjectGrant(param="node", rationale="now demoted")}
        violations = collect_all_violations(Path("pipelex"), grants=grants)
        assert [violation.kind for violation in violations] == [ViolationKind.DEAD_GRANT]

    def test_dead_grant_for_newly_exempt_def_flagged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A def that became carved-out (e.g. @override) no longer holds its grant — forces a registry decision."""
        source_root = tmp_path / "pipelex" / "sample"
        source_root.mkdir(parents=True)
        (source_root / "module.py").write_text(
            "class Impl:\n    @override\n    def render(self, node):\n        return node\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        grants = {"pipelex/sample/module.py::Impl.render": SubjectGrant(param="node", rationale="now overridden")}
        violations = collect_all_violations(Path("pipelex"), grants=grants)
        assert [violation.kind for violation in violations] == [ViolationKind.DEAD_GRANT]

    def test_live_grant_not_flagged_even_while_def_violates_missing_star(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A granted def that grew a second positional param reports missing-star only — the grant stays alive."""
        source_root = tmp_path / "pipelex" / "sample"
        source_root.mkdir(parents=True)
        (source_root / "module.py").write_text("def render(node, extra):\n    return node\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        grants = {"pipelex/sample/module.py::render": SubjectGrant(param="node", rationale="ok")}
        violations = collect_all_violations(Path("pipelex"), grants=grants)
        assert [violation.kind for violation in violations] == [ViolationKind.MISSING_STAR]


class TestSubjectGrantRegistryOrder:
    """The registry is rewritten sorted by key on every write, so file order is an invariant — one a bulk
    path rewrite breaks silently, since an unsorted registry parses and grants exactly the same subjects.
    """

    def test_sorted_registry_has_no_order_violation(self, tmp_path: Path) -> None:
        _write_registry(tmp_path, content=_SORTED_REGISTRY)
        assert find_unsorted_grants(grants=load_subject_grants(root=tmp_path), root=tmp_path) == []

    def test_out_of_order_entry_flagged(self, tmp_path: Path) -> None:
        """The two entries of `_VALID_REGISTRY` are written in the reverse of their sorted order."""
        _write_registry(tmp_path, content=_VALID_REGISTRY)
        violations = find_unsorted_grants(grants=load_subject_grants(root=tmp_path), root=tmp_path)
        assert [violation.kind for violation in violations] == [ViolationKind.UNSORTED_GRANT]
        assert violations[0].key == "pipelex/sample/module.py::Builder.build"
        assert violations[0].lineno == 0, "the line belongs to the registry, not to a def — it travels in `detail`"
        assert "subject_grants.toml:7" in violations[0].detail
        assert "pipelex/sample/module.py::render" in violations[0].detail

    def test_missing_registry_is_an_explicit_error(self, tmp_path: Path) -> None:
        with pytest.raises(SubjectGrantRegistryError, match="not found"):
            find_unsorted_grants(grants={}, root=tmp_path)

    def test_entry_the_scan_cannot_read_is_an_explicit_error(self, tmp_path: Path) -> None:
        """A multi-line rationale can carry a line that looks like a table header — the scan must not
        silently disagree with the parser about which entries exist, or the order rule quietly narrows.
        """
        _write_registry(tmp_path, content=_PHANTOM_HEADER_REGISTRY)
        with pytest.raises(SubjectGrantRegistryError, match="the order check cannot read"):
            find_unsorted_grants(grants=load_subject_grants(root=tmp_path), root=tmp_path)
