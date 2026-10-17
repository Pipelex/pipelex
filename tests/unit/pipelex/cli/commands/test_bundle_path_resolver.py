"""Unit tests for the human CLI shared bundle-path resolver.

``pipelex validate bundle`` and ``pipelex fix bundle`` resolve their ``path`` argument through ``resolve_bundle_target``,
which reads a folder whole, and ``pipelex build inputs bundle`` and ``pipelex build output bundle`` through
``resolve_build_bundle_target``, which acts on the pipe ``run bundle`` starts the same folder at, so their semantics
are pinned here once for every command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.bundle_target_resolution import resolve_method_folder_run
from pipelex.cli.commands.bundle_path_resolver import JudgedBundleTarget, resolve_build_bundle_target, resolve_bundle_target
from pipelex.pipeline.exceptions import ValidateBundleError
from tests.helpers.method_folders import NAMED_PIPE, MethodFolderShape, write_method_folder

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_HINT = "  To fix a bundle, pass a .mthds file or directory: pipelex fix bundle <path>"
_RESOLVER_MODULE = "pipelex.cli.commands.bundle_path_resolver"


def _run_refusal(*, directory: Path) -> str:
    """The message `run bundle` refuses the folder with."""
    with pytest.raises(ValidateBundleError) as exc_info:
        resolve_method_folder_run(directory=directory, pipe_override=None)
    return exc_info.value.message


class TestHumanBundlePathResolver:
    def test_mthds_file_is_taken_as_is(self, tmp_path: Path) -> None:
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        target = resolve_bundle_target(str(bundle_file), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert target == JudgedBundleTarget(bundle_path=bundle_file, method_dir=None, library_dirs=None)

    def test_tilde_in_path_is_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        target = resolve_bundle_target("~/my_bundle.mthds", library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert target.bundle_path == bundle_file

    def test_tilde_in_library_dir_is_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()

        target = resolve_bundle_target(str(bundle_file), library_dir=["~/libs"], command="fix", not_a_bundle_hint=_HINT)

        assert target.library_dirs == [libs_dir]

    @pytest.mark.parametrize("shape", list(MethodFolderShape))
    def test_a_folder_is_judged_whole_whatever_its_main_pipes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], shape: MethodFolderShape
    ) -> None:
        """No pipe to start at is needed: several main pipes, or none, are no refusal, since every bundle is judged."""
        write_method_folder(directory=tmp_path, shape=shape)

        target = resolve_bundle_target(str(tmp_path), library_dir=None, command="validate", not_a_bundle_hint=_HINT)

        assert target == JudgedBundleTarget(bundle_path=None, method_dir=tmp_path, library_dirs=[tmp_path])
        assert "main pipe" not in capsys.readouterr().out

    def test_directory_is_prepended_to_existing_library_dirs_without_duplication(self, tmp_path: Path) -> None:
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.SEVERAL_MAIN_PIPES)
        other_dir = tmp_path.parent / f"{tmp_path.name}-libs"
        other_dir.mkdir()

        target = resolve_bundle_target(str(tmp_path), library_dir=[str(other_dir)], command="fix", not_a_bundle_hint=_HINT)
        assert target.library_dirs == [tmp_path, other_dir]

        target_again = resolve_bundle_target(
            str(tmp_path),
            library_dir=[str(tmp_path), str(other_dir)],
            command="fix",
            not_a_bundle_hint=_HINT,
        )
        assert target_again.library_dirs == [tmp_path, other_dir]

    @pytest.mark.parametrize("files", [{}, {".DS_Store": "", "notes.md": "# Notes\n"}], ids=["empty", "no_bundle"])
    def test_a_folder_holding_no_bundle_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]) -> None:
        """An empty folder, or one whose tree keeps no bundle, has nothing to judge: no verdict."""
        for name, content in files.items():
            (tmp_path / name).write_text(content, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path), library_dir=None, command="validate", not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 2
        assert f"Failed to validate: The folder '{tmp_path}' holds no .mthds bundle." in capsys.readouterr().err

    def test_a_folder_whose_tree_is_refused_is_the_invalid_verdict(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A symbolic link in the tree is refused when the tree is listed, as `validate` reports an invalid bundle."""
        mock_handler = mocker.patch(f"{_RESOLVER_MODULE}.handle_validate_bundle_error", side_effect=typer.Exit(1))
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)
        outside_bundle = tmp_path.parent / f"{tmp_path.name}-outside.mthds"
        outside_bundle.write_text('domain = "outside"\n', encoding="utf-8")
        (tmp_path / "linked.mthds").symlink_to(outside_bundle)

        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 1
        verdict = mock_handler.call_args.args[0]
        assert isinstance(verdict, ValidateBundleError)
        assert "linked.mthds" in verdict.message

    def test_not_a_bundle_path_exits_2_with_command_hint(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            resolve_bundle_target(str(tmp_path / "nope.txt"), library_dir=None, command="fix", not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "Failed to fix:" in err
        assert "is not a .mthds file or directory" in err
        assert "pipelex fix bundle <path>" in err

    @pytest.mark.parametrize("shape", [MethodFolderShape.MANIFEST_MAIN_PIPE, MethodFolderShape.ONE_DECLARED_MAIN_PIPE])
    def test_a_build_command_acts_on_the_pipe_a_run_of_the_folder_starts_at(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], shape: MethodFolderShape
    ) -> None:
        write_method_folder(directory=tmp_path, shape=shape)
        assert shape.entry is not None

        target = resolve_build_bundle_target(path=str(tmp_path), library_dir=None, pipe_override=None, not_a_bundle_hint=_HINT)
        assert f"Using the method's main pipe {shape.entry.pipe_ref}, in {shape.entry.tree_path}" in capsys.readouterr().out

        assert target.bundle_path == (tmp_path / shape.entry.tree_path).resolve()
        assert target.pipe_code == shape.entry.pipe_ref
        assert target.library_dir == [str(tmp_path)]
        assert target.default_output_dir == tmp_path

    def test_a_build_command_naming_its_pipe_loads_the_folder_as_its_library(self, tmp_path: Path) -> None:
        """With `--pipe`, several main pipes are no ambiguity, and the pipe is looked up in the method, as a run does."""
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.SEVERAL_MAIN_PIPES)

        target = resolve_build_bundle_target(path=str(tmp_path), library_dir=None, pipe_override=NAMED_PIPE.pipe_ref, not_a_bundle_hint=_HINT)

        assert target.bundle_path is None
        assert target.pipe_code == NAMED_PIPE.pipe_ref
        assert target.library_dir == [str(tmp_path)]
        assert target.default_output_dir == tmp_path

    def test_a_build_command_on_a_bundle_file_writes_beside_it(self, tmp_path: Path) -> None:
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        target = resolve_build_bundle_target(path=str(bundle_file), library_dir=None, pipe_override="my_pipe", not_a_bundle_hint=_HINT)

        assert target.bundle_path == bundle_file
        assert target.pipe_code == "my_pipe"
        assert target.library_dir is None
        assert target.default_output_dir is None

    @pytest.mark.parametrize("shape", [MethodFolderShape.SEVERAL_MAIN_PIPES, MethodFolderShape.NO_MAIN_PIPE])
    def test_a_build_command_on_a_folder_with_no_single_main_pipe_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], shape: MethodFolderShape
    ) -> None:
        write_method_folder(directory=tmp_path, shape=shape)
        assert shape.refusal is not None

        with pytest.raises(typer.Exit) as exc_info:
            resolve_build_bundle_target(path=str(tmp_path), library_dir=None, pipe_override=None, not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 1
        err = capsys.readouterr().err
        assert f"Failed to run: {_run_refusal(directory=tmp_path)}" in err
        assert shape.refusal in err

    def test_a_build_command_on_a_folder_holding_no_bundle_exits_1_with_the_message_run_gives(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            resolve_build_bundle_target(path=str(tmp_path), library_dir=None, pipe_override=None, not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 1
        run_refusal = _run_refusal(directory=tmp_path)
        assert "holds no .mthds bundle, so it has no pipe to start at" in run_refusal
        assert f"Failed to run: {run_refusal}" in capsys.readouterr().err

    def test_a_build_command_on_a_path_that_is_no_bundle_exits_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            resolve_build_bundle_target(path=str(tmp_path / "nope.txt"), library_dir=None, pipe_override=None, not_a_bundle_hint=_HINT)

        assert exc_info.value.exit_code == 1
        err = capsys.readouterr().err
        assert "Failed to run:" in err
        assert "is not a .mthds file or directory" in err
