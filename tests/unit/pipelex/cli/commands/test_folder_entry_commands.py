"""The human commands taking a method's folder: `validate` and `fix` judge it whole, `build` acts on the pipe `run` starts at."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.bundle_target_resolution import resolve_method_folder_run
from pipelex.cli.commands.build.inputs.bundle_cmd import build_inputs_bundle_cmd
from pipelex.cli.commands.build.output.bundle_cmd import build_output_bundle_cmd
from pipelex.cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.validate.bundle_cmd import validate_bundle_cmd
from pipelex.pipeline.exceptions import MethodEntryError
from tests.helpers.method_folders import NAMED_PIPE, MethodFolderShape, write_method_folder

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_RESOLVED_SHAPES = [MethodFolderShape.MANIFEST_MAIN_PIPE, MethodFolderShape.ONE_DECLARED_MAIN_PIPE]
_REFUSED_SHAPES = [MethodFolderShape.SEVERAL_MAIN_PIPES, MethodFolderShape.NO_MAIN_PIPE]
_BUILD_COMMANDS = ["build_inputs", "build_output"]


def _run_refusal(*, directory: Path) -> str:
    """The message `run bundle` refuses the folder with: no single pipe to start at is the run's own refusal, no verdict."""
    with pytest.raises(MethodEntryError) as exc_info:
        resolve_method_folder_run(directory=directory, pipe_override=None)
    return exc_info.value.message


def _invoke_validate_or_fix(*, command: str, path: Path) -> None:
    match command:
        case "validate":
            validate_bundle_cmd(path=str(path))
        case "fix":
            fix_bundle_cmd(path=str(path))
        case _:
            msg = f"Unknown command '{command}'"
            raise ValueError(msg)


def _invoke_build(*, command: str, path: Path, pipe: str | None) -> None:
    match command:
        case "build_inputs":
            build_inputs_bundle_cmd(path=str(path), pipe=pipe)
        case "build_output":
            build_output_bundle_cmd(path=str(path), pipe=pipe)
        case _:
            msg = f"Unknown build command '{command}'"
            raise ValueError(msg)


def _invoke_folder_command(*, command: str, path: Path) -> None:
    """Any command reading a folder, with no `--pipe`."""
    match command:
        case "validate" | "fix":
            _invoke_validate_or_fix(command=command, path=path)
        case "run":
            run_bundle_cmd(path=str(path))
        case _:
            _invoke_build(command=command, path=path, pipe=None)


def _build_command_name(*, command: str) -> str:
    """The command as its failures name it."""
    return command.replace("_", " ")


def _write_folder_with_a_refused_tree(*, directory: Path) -> None:
    """A method folder whose tree is refused when it is listed: a symbolic link among its files."""
    write_method_folder(directory=directory, shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)
    outside_bundle = directory.parent / f"{directory.name}-outside.mthds"
    outside_bundle.write_text('domain = "outside"\n', encoding="utf-8")
    (directory / "linked.mthds").symlink_to(outside_bundle)


def _build_executor(*, command: str) -> str:
    match command:
        case "build_inputs":
            return "pipelex.cli.commands.build.inputs.bundle_cmd.execute_generate_inputs"
        case "build_output":
            return "pipelex.cli.commands.build.output.bundle_cmd.execute_generate_output"
        case _:
            msg = f"Unknown build command '{command}'"
            raise ValueError(msg)


class TestHumanFolderEntryCommands:
    @pytest.mark.parametrize("shape", list(MethodFolderShape))
    def test_validate_judges_the_whole_method_whatever_its_main_pipes(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        """Every bundle of the folder is judged, as the protocol's validation judges a method, so no pipe to start at is needed."""
        mock_execute = mocker.patch("pipelex.cli.commands.validate.bundle_cmd.execute_validate")
        write_method_folder(directory=tmp_path, shape=shape)

        validate_bundle_cmd(path=str(tmp_path))

        kwargs = mock_execute.call_args.kwargs
        assert kwargs["method_dir"] == tmp_path
        assert kwargs["bundle_path"] is None
        assert kwargs["library_dirs"] == [tmp_path]
        assert kwargs["pipe_code"] is None

    @pytest.mark.parametrize("shape", list(MethodFolderShape))
    def test_fix_patches_the_whole_method_validate_judges(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        mock_execute = mocker.patch("pipelex.cli.commands.fix.bundle_cmd.execute_fix")
        write_method_folder(directory=tmp_path, shape=shape)

        fix_bundle_cmd(path=str(tmp_path))

        target = mock_execute.call_args.kwargs["target"]
        assert target.method_dir == tmp_path
        assert target.bundle_path is None
        assert target.library_dirs == [tmp_path]
        assert target.judged_path == tmp_path

    def test_validate_names_the_folder_whose_tree_is_refused_in_its_invalid_verdict(self, mocker: MockerFixture, tmp_path: Path) -> None:
        recorded_console = Console(width=500, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_error_console", return_value=recorded_console)
        mock_execute = mocker.patch("pipelex.cli.commands.validate.bundle_cmd.execute_validate")
        _write_folder_with_a_refused_tree(directory=tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            validate_bundle_cmd(path=str(tmp_path))

        assert exc_info.value.exit_code == 1
        output = recorded_console.export_text()
        assert "Bundle validation failed" in output
        assert f"Bundle: {tmp_path}" in output
        assert "linked.mthds" in output
        mock_execute.assert_not_called()

    @pytest.mark.parametrize("diff", [False, True], ids=["fix", "preview"])
    def test_fix_reports_a_folder_whose_tree_is_refused_as_a_fix_that_fails(self, mocker: MockerFixture, tmp_path: Path, diff: bool) -> None:
        recorded_console = Console(width=500, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.fix._fix_core.get_console", return_value=recorded_console)
        mocker.patch("pipelex.cli.error_handlers.get_error_console", return_value=recorded_console)
        mock_execute = mocker.patch("pipelex.cli.commands.fix.bundle_cmd.execute_fix")
        _write_folder_with_a_refused_tree(directory=tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(tmp_path), diff=diff)

        assert exc_info.value.exit_code == 1
        output = recorded_console.export_text()
        assert ("the bundle would still be invalid" if diff else "Bundle could not be fully fixed") in output
        assert "Bundle validation failed" not in output
        assert f"Bundle: {tmp_path}" in output
        assert "linked.mthds" in output
        mock_execute.assert_not_called()

    @pytest.mark.parametrize("command", ["validate", "fix"])
    def test_validate_and_fix_refuse_a_folder_holding_no_bundle_with_no_verdict(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
    ) -> None:
        mock_validate = mocker.patch("pipelex.cli.commands.validate.bundle_cmd.execute_validate")
        mock_fix = mocker.patch("pipelex.cli.commands.fix.bundle_cmd.execute_fix")

        with pytest.raises(typer.Exit) as exc_info:
            _invoke_validate_or_fix(command=command, path=tmp_path)

        assert exc_info.value.exit_code == 2
        assert f"Failed to {command}: The folder '{tmp_path}' holds no .mthds bundle." in capsys.readouterr().err
        mock_validate.assert_not_called()
        mock_fix.assert_not_called()

    @pytest.mark.parametrize(("command", "exit_code"), [("validate", 2), ("fix", 2), ("run", 1), ("build_inputs", 1), ("build_output", 1)])
    def test_a_configuration_that_does_not_validate_before_the_boot_is_reported_as_a_failed_boot(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str, exit_code: int
    ) -> None:
        """Listing the tree reads its limits from the configuration: a refusal there names the command, never a traceback.

        `validate` and `fix` exit 2 on it, no verdict, as the agent CLI's `validate bundle` and `fix bundle` do; `run`
        and `build` exit 1, as their other failures do.
        """
        mocker.patch("pipelex.libraries.method_trees.local_tree_limits", side_effect=PipelexConfigError("the configuration is out of date"))
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)

        with pytest.raises(typer.Exit) as exc_info:
            _invoke_folder_command(command=command, path=tmp_path)

        assert exc_info.value.exit_code == exit_code
        assert f"Failed to {_build_command_name(command=command)}: the configuration is out of date" in capsys.readouterr().err

    @pytest.mark.parametrize("shape", _RESOLVED_SHAPES)
    @pytest.mark.parametrize("command", _BUILD_COMMANDS)
    def test_build_acts_on_the_pipe_the_method_starts_at_and_writes_in_the_folder(
        self, mocker: MockerFixture, tmp_path: Path, command: str, shape: MethodFolderShape
    ) -> None:
        mock_execute = mocker.patch(_build_executor(command=command))
        write_method_folder(directory=tmp_path, shape=shape)
        assert shape.entry is not None

        _invoke_build(command=command, path=tmp_path, pipe=None)

        kwargs = mock_execute.call_args.kwargs
        assert kwargs["pipe_code"] == shape.entry.pipe_ref
        assert kwargs["bundle_path"] == (tmp_path / shape.entry.tree_path).resolve()
        assert kwargs["library_dir"] == [str(tmp_path)]
        assert kwargs["default_output_dir"] == tmp_path
        assert kwargs["output_path"] is None

    @pytest.mark.parametrize("command", _BUILD_COMMANDS)
    def test_build_naming_its_pipe_loads_the_folder_as_its_library(self, mocker: MockerFixture, tmp_path: Path, command: str) -> None:
        """With `--pipe`, several main pipes are no ambiguity, and the pipe is looked up in the method, as a run does."""
        mock_execute = mocker.patch(_build_executor(command=command))
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.SEVERAL_MAIN_PIPES)

        _invoke_build(command=command, path=tmp_path, pipe=NAMED_PIPE.pipe_ref)

        kwargs = mock_execute.call_args.kwargs
        assert kwargs["pipe_code"] == NAMED_PIPE.pipe_ref
        assert kwargs["bundle_path"] is None
        assert kwargs["library_dir"] == [str(tmp_path)]
        assert kwargs["default_output_dir"] == tmp_path

    @pytest.mark.parametrize("shape", _REFUSED_SHAPES)
    @pytest.mark.parametrize("command", _BUILD_COMMANDS)
    def test_build_refuses_a_folder_with_no_single_main_pipe(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str, shape: MethodFolderShape
    ) -> None:
        mock_execute = mocker.patch(_build_executor(command=command))
        write_method_folder(directory=tmp_path, shape=shape)

        with pytest.raises(typer.Exit) as exc_info:
            _invoke_build(command=command, path=tmp_path, pipe=None)

        assert exc_info.value.exit_code == 1
        assert f"Failed to {_build_command_name(command=command)}: {_run_refusal(directory=tmp_path)}" in capsys.readouterr().err
        mock_execute.assert_not_called()

    @pytest.mark.parametrize("command", _BUILD_COMMANDS)
    def test_build_on_a_bundle_file_keeps_its_pipe_and_writes_beside_it(self, mocker: MockerFixture, tmp_path: Path, command: str) -> None:
        mock_execute = mocker.patch(_build_executor(command=command))
        bundle_file = tmp_path / "my_bundle.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        _invoke_build(command=command, path=bundle_file, pipe="my_pipe")

        kwargs = mock_execute.call_args.kwargs
        assert kwargs["pipe_code"] == "my_pipe"
        assert kwargs["bundle_path"] == bundle_file
        assert kwargs["library_dir"] is None
        assert kwargs["default_output_dir"] is None
