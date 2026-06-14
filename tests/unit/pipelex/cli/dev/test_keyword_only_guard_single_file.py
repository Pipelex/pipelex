"""Unit tests for the single-file surface of the keyword-only guard (filesystem + lean CLI entry)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    collect_all_violations,
    collect_violations_for_files,
    main,
    relative_source_path,
)

_BAD_SOURCE = "def f(a, b):\n    return a\n"
_GOOD_SOURCE = "def g(subject, *, opt):\n    return opt\n"


def _make_tree(root: Path) -> None:
    """Create a minimal pipelex source tree with one violating and one compliant module."""
    sample = root / "pipelex" / "sample"
    sample.mkdir(parents=True)
    (sample / "bad.py").write_text(_BAD_SOURCE, encoding="utf-8")
    (sample / "good.py").write_text(_GOOD_SOURCE, encoding="utf-8")


class TestKeywordOnlyGuardSingleFile:
    def test_single_file_matches_full_scan(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A single-file scan is an exact subset of the full-tree scan for that file (the equivalence contract).

        Mirrors production, where the full scan runs against the *relative* ``SOURCE_ROOT`` (``Path("pipelex")``),
        so both sides report repo-root-relative paths.
        """
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        single = collect_violations_for_files([Path("pipelex/sample/bad.py")])
        full = collect_all_violations(Path("pipelex"))
        assert [violation.key for violation in single] == [violation.key for violation in full]
        assert len(single) == 1
        assert single[0].relative_path == "pipelex/sample/bad.py"
        assert single[0].qualified_name == "f"

    def test_compliant_file_has_no_violations(self, tmp_path: Path) -> None:
        _make_tree(tmp_path)
        assert collect_violations_for_files([Path("pipelex/sample/good.py")], root=tmp_path) == []

    def test_absolute_path_is_handled(self, tmp_path: Path) -> None:
        _make_tree(tmp_path)
        abs_path = tmp_path / "pipelex" / "sample" / "bad.py"
        result = collect_violations_for_files([abs_path], root=tmp_path)
        assert len(result) == 1
        assert result[0].qualified_name == "f"

    def test_out_of_scope_path_skipped(self, tmp_path: Path) -> None:
        """A .py file outside pipelex/ is not the guard's concern."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "thing.py").write_text(_BAD_SOURCE, encoding="utf-8")
        assert collect_violations_for_files([Path("tests/thing.py")], root=tmp_path) == []

    def test_syntax_error_file_skipped(self, tmp_path: Path) -> None:
        """A mid-edit file that does not parse yet is skipped, never raised — the hook must not block on it."""
        (tmp_path / "pipelex").mkdir()
        (tmp_path / "pipelex" / "broken.py").write_text("def f(a, b\n", encoding="utf-8")
        assert collect_violations_for_files([Path("pipelex/broken.py")], root=tmp_path) == []

    def test_missing_file_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "pipelex").mkdir()
        assert collect_violations_for_files([Path("pipelex/ghost.py")], root=tmp_path) == []

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

    def test_main_returns_0_for_compliant(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        exit_code = main(["pipelex/sample/good.py"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""
