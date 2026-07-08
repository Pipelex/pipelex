"""Unit tests for the human CLI shared bundle-path resolver.

``pipelex validate bundle`` and ``pipelex fix bundle`` resolve their ``path`` argument through
this one helper — fix must patch exactly the file validate judged — so its semantics are pinned
here once for both commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.commands.bundle_path_resolver import resolve_bundle_target

if TYPE_CHECKING:
    from pathlib import Path

_HINT = "  To fix a bundle, pass a .mthds file or directory: pipelex fix bundle <path>"


class TestHumanBundlePathResolver:
    def test_mthds_file_is_taken_as_is(self, tmp_path: Path) -> None:
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        bundle_path, library_dir = resolve_bundle_target(str(bundle_file), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert bundle_path == str(bundle_file)
        assert library_dir is None

    def test_tilde_in_path_is_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        bundle_path, _ = resolve_bundle_target("~/my_bundle.mthds", library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert bundle_path == str(bundle_file)

    def test_tilde_in_library_dir_is_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()

        _, library_dir = resolve_bundle_target(str(bundle_file), library_dir=["~/libs"], command="fix", not_a_bundle_hint=_HINT)

        assert library_dir == [str(libs_dir)]

    def test_directory_with_default_bundle_name_auto_detects_and_injects_dir(self, tmp_path: Path) -> None:
        bundle_file = tmp_path / DEFAULT_BUNDLE_FILE_NAME
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")
        (tmp_path / "sibling.mthds").write_text('domain = "sibling"\n', encoding="utf-8")

        bundle_path, library_dir = resolve_bundle_target(str(tmp_path), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert bundle_path == str(bundle_file)
        assert library_dir == [str(tmp_path)]

    def test_directory_with_single_mthds_falls_back_to_it(self, tmp_path: Path) -> None:
        bundle_file = tmp_path / "only_one.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        bundle_path, library_dir = resolve_bundle_target(str(tmp_path), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert bundle_path == str(bundle_file)
        assert library_dir == [str(tmp_path)]

    def test_directory_is_prepended_to_existing_library_dirs_without_duplication(self, tmp_path: Path) -> None:
        bundle_file = tmp_path / DEFAULT_BUNDLE_FILE_NAME
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")
        other_dir = tmp_path / "libs"
        other_dir.mkdir()

        _, library_dir = resolve_bundle_target(str(tmp_path), library_dir=[str(other_dir)], command="fix", not_a_bundle_hint=_HINT)
        assert library_dir == [str(tmp_path), str(other_dir)]

        _, library_dir_again = resolve_bundle_target(
            str(tmp_path),
            library_dir=[str(tmp_path), str(other_dir)],
            command="fix",
            not_a_bundle_hint=_HINT,
        )
        assert library_dir_again == [str(tmp_path), str(other_dir)]

    def test_empty_directory_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 2
        assert "Failed to fix: no .mthds bundle file found" in capsys.readouterr().err

    def test_ambiguous_directory_exits_2_naming_the_candidates(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / "a.mthds").write_text('domain = "a"\n', encoding="utf-8")
        (tmp_path / "b.mthds").write_text('domain = "b"\n', encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "multiple .mthds files found" in err
        assert "a.mthds" in err
        assert "b.mthds" in err
        assert "pipelex fix bundle" in err

    def test_not_a_bundle_path_exits_2_with_command_hint(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path / "nope.txt"), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "Failed to fix:" in err
        assert "is not a .mthds file or directory" in err
        assert "pipelex fix bundle <path>" in err
