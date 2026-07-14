"""Unit tests for the single-file surface of the keyword-only guard (filesystem + lean CLI entry)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    collect_all_violations,
    collect_violations_for_files,
    load_subject_grants,
    main,
    relative_source_path,
)

_BAD_SOURCE = "def f(a, b):\n    return a\n"
_GOOD_SOURCE = "def g(*, subject, opt):\n    return opt\n"
_GRANTED_SOURCE = "def render(node):\n    return node\n"


def _make_tree(root: Path) -> None:
    """Create a minimal repo tree: violating, compliant, and granted modules, plus the registry."""
    sample = root / "pipelex" / "sample"
    sample.mkdir(parents=True)
    (sample / "bad.py").write_text(_BAD_SOURCE, encoding="utf-8")
    (sample / "good.py").write_text(_GOOD_SOURCE, encoding="utf-8")
    (sample / "granted.py").write_text(_GRANTED_SOURCE, encoding="utf-8")
    (root / "subject_grants.toml").write_text(
        'version = 1\n\n["pipelex/sample/granted.py::render"]\nparam = "node"\nrationale = "test grant"\n',
        encoding="utf-8",
    )


class TestKeywordOnlyGuardSingleFile:
    def test_single_file_matches_full_scan(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A single-file scan is an exact subset of the full-tree scan for that file (the equivalence contract).

        Mirrors production, where the full scan runs against the *relative* ``SOURCE_ROOT`` (``Path("pipelex")``),
        so both sides report repo-root-relative paths.
        """
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        single = collect_violations_for_files([Path("pipelex/sample/bad.py")], grants={})
        full = collect_all_violations(Path("pipelex"), grants={})
        assert [violation.key for violation in single] == [violation.key for violation in full if violation.relative_path.endswith("bad.py")]
        assert len(single) == 1
        assert single[0].relative_path == "pipelex/sample/bad.py"
        assert single[0].qualified_name == "f"

    def test_compliant_file_has_no_violations(self, tmp_path: Path) -> None:
        _make_tree(tmp_path)
        assert collect_violations_for_files([Path("pipelex/sample/good.py")], root=tmp_path, grants={}) == []

    def test_granted_file_has_no_violations(self, tmp_path: Path) -> None:
        """The lean per-file path honors the grants it is given — a granted subject is clean."""
        _make_tree(tmp_path)
        grants = load_subject_grants(root=tmp_path)
        assert collect_violations_for_files([Path("pipelex/sample/granted.py")], root=tmp_path, grants=grants) == []

    def test_absolute_path_is_handled(self, tmp_path: Path) -> None:
        _make_tree(tmp_path)
        abs_path = tmp_path / "pipelex" / "sample" / "bad.py"
        result = collect_violations_for_files([abs_path], root=tmp_path, grants={})
        assert len(result) == 1
        assert result[0].qualified_name == "f"

    def test_out_of_scope_path_skipped(self, tmp_path: Path) -> None:
        """A .py file outside pipelex/ is not the guard's concern."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "thing.py").write_text(_BAD_SOURCE, encoding="utf-8")
        assert collect_violations_for_files([Path("tests/thing.py")], root=tmp_path, grants={}) == []

    def test_syntax_error_file_skipped(self, tmp_path: Path) -> None:
        """A mid-edit file that does not parse yet is skipped, never raised — the hook must not block on it."""
        (tmp_path / "pipelex").mkdir()
        (tmp_path / "pipelex" / "broken.py").write_text("def f(a, b\n", encoding="utf-8")
        assert collect_violations_for_files([Path("pipelex/broken.py")], root=tmp_path, grants={}) == []

    def test_missing_file_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "pipelex").mkdir()
        assert collect_violations_for_files([Path("pipelex/ghost.py")], root=tmp_path, grants={}) == []

    @pytest.mark.parametrize(
        "relative",
        [
            "pipelex/sample/note.md",  # non-.py
            "tests/thing.py",  # outside pipelex/
        ],
    )
    def test_relative_source_path_rejects_out_of_scope(self, tmp_path: Path, relative: str) -> None:
        assert relative_source_path(Path(relative), root=tmp_path) is None

    def test_relative_source_path_accepts_in_scope(self, tmp_path: Path) -> None:
        _make_tree(tmp_path)
        resolved = relative_source_path(tmp_path / "pipelex" / "sample" / "bad.py", root=tmp_path)
        assert resolved == Path("pipelex/sample/bad.py")

    def test_relative_source_path_rejects_pycache(self, tmp_path: Path) -> None:
        target = tmp_path / "pipelex" / "__pycache__" / "x.py"
        target.parent.mkdir(parents=True)
        target.write_text(_GOOD_SOURCE, encoding="utf-8")
        assert relative_source_path(target, root=tmp_path) is None

    def test_main_returns_2_and_prints_for_violation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        exit_code = main(["pipelex/sample/bad.py"])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "pipelex/sample/bad.py:1" in captured.err
        assert "f" in captured.err
        assert "missing-star" in captured.err  # the violation's kind and its remedy are named

    def test_main_reads_the_registry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """The lean entrypoint loads subject_grants.toml itself — a granted subject passes, an ungranted one blocks."""
        _make_tree(tmp_path)
        (tmp_path / "pipelex" / "sample" / "ungranted.py").write_text("def render(node):\n    return node\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert main(["pipelex/sample/granted.py"]) == 0
        exit_code = main(["pipelex/sample/ungranted.py"])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "ungranted-subject" in captured.err
        assert "make subject-grant" in captured.err

    def test_main_returns_2_when_registry_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """A missing registry is an explicit check error, never a silent empty registry."""
        _make_tree(tmp_path)
        (tmp_path / "subject_grants.toml").unlink()
        monkeypatch.chdir(tmp_path)
        exit_code = main(["pipelex/sample/good.py"])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "could not run" in captured.err
        assert "subject_grants.toml" in captured.err

    def test_main_returns_0_for_compliant(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        exit_code = main(["pipelex/sample/good.py"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""
