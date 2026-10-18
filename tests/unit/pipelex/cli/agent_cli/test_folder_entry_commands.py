"""The agent commands taking a method's folder: `validate` and `fix` judge it whole, `inputs` acts on the pipe `run` starts at."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
import typer

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.cli.agent_cli.commands.inputs.bundle_cmd import inputs_bundle_cmd
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd
from pipelex.cli.bundle_target_resolution import resolve_method_folder_run
from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from tests.helpers.method_folders import NAMED_PIPE, MethodFolderShape, write_method_folder

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture, MockType

VALIDATE_MODULE = "pipelex.cli.agent_cli.commands.validate.bundle_cmd"
FIX_MODULE = "pipelex.cli.agent_cli.commands.fix.bundle_cmd"
INPUTS_MODULE = "pipelex.cli.agent_cli.commands.inputs.bundle_cmd"
JUDGED_TARGET_MODULE = "pipelex.cli.judged_target"

_RESOLVED_SHAPES = [MethodFolderShape.MANIFEST_MAIN_PIPE, MethodFolderShape.ONE_DECLARED_MAIN_PIPE]
_UNDECIDED_SHAPES = [MethodFolderShape.SEVERAL_MAIN_PIPES, MethodFolderShape.NO_MAIN_PIPE]
_VALID_RESULT: dict[str, Any] = {"success": True, "is_valid": True, "is_runnable": True, "validated_pipes": []}


def _run_refusal(*, directory: Path) -> str:
    """The message `run bundle` refuses the folder with: no single pipe to start at is the run's own refusal, no verdict."""
    with pytest.raises(MethodEntryError) as exc_info:
        resolve_method_folder_run(directory=directory, pipe_override=None)
    return exc_info.value.message


class _ValidateMocks(NamedTuple):
    """The validate cores and graph helpers a test reads the calls of."""

    whole: MockType
    sliced: MockType
    folder: MockType
    graph: MockType
    view: MockType
    success: MockType


def _invoke_validate_or_fix_for_json(*, command: str, path: Path) -> None:
    match command:
        case "validate":
            validate_bundle_cmd(path=str(path), error_format=CliOutputFormat.JSON)
        case "fix":
            fix_bundle_cmd(path=str(path), error_format=CliOutputFormat.JSON)
        case _:
            msg = f"Unknown command '{command}'"
            raise ValueError(msg)


def _invoke_pre_boot_command(*, command: str, path: Path) -> None:
    """Invoke a command taking a method's folder, its errors in JSON."""
    match command:
        case "validate" | "fix":
            _invoke_validate_or_fix_for_json(command=command, path=path)
        case "inputs":
            inputs_bundle_cmd(path=str(path))
        case "run":
            run_bundle_cmd(path=str(path), error_format=CliOutputFormat.JSON)
        case _:
            msg = f"Unknown command '{command}'"
            raise ValueError(msg)


def _write_folder_with_a_refused_tree(*, directory: Path) -> None:
    """A method folder whose tree is refused when it is listed: a symbolic link among its files."""
    write_method_folder(directory=directory, shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)
    outside_bundle = directory.parent / f"{directory.name}-outside.mthds"
    outside_bundle.write_text('domain = "outside"\n', encoding="utf-8")
    (directory / "linked.mthds").symlink_to(outside_bundle)


def _patch_validate(mocker: MockerFixture) -> _ValidateMocks:
    """Stub what `validate bundle` boots and runs; return its cores, its graph helpers and its success emitter."""
    mocker.patch(f"{VALIDATE_MODULE}.make_pipelex_for_agent_cli")
    mocker.patch(f"{VALIDATE_MODULE}.Pipelex.teardown_if_needed")
    return _ValidateMocks(
        whole=mocker.patch(f"{VALIDATE_MODULE}.validate_bundle_core", new=mocker.AsyncMock(return_value=dict(_VALID_RESULT))),
        sliced=mocker.patch(f"{VALIDATE_MODULE}.validate_pipe_in_bundle_core", new=mocker.AsyncMock(return_value=dict(_VALID_RESULT))),
        folder=mocker.patch(f"{VALIDATE_MODULE}.validate_method_folder_core", new=mocker.AsyncMock(return_value=dict(_VALID_RESULT))),
        graph=mocker.patch(f"{VALIDATE_MODULE}.generate_graph_for_bundle", new=mocker.AsyncMock(return_value={"graph_files": {}})),
        view=mocker.patch(f"{VALIDATE_MODULE}.generate_view_for_bundle", new=mocker.AsyncMock(return_value={"graphspec": {}})),
        success=mocker.patch(f"{VALIDATE_MODULE}.agent_success_formatted"),
    )


def _patch_fix(mocker: MockerFixture) -> MockType:
    mocker.patch(f"{FIX_MODULE}.make_pipelex_for_agent_cli")
    mocker.patch(f"{FIX_MODULE}.Pipelex.teardown_if_needed")
    mocker.patch(f"{FIX_MODULE}.agent_success_formatted")
    result = FixBundleResult(is_valid=True, iterations=0, fixes_applied=[], remaining_errors=[], is_runnable=True)
    mocker.patch(f"{JUDGED_TARGET_MODULE}.fix_bundle_file", new=mocker.AsyncMock(return_value=result))
    mock_fix: MockType = mocker.patch(f"{JUDGED_TARGET_MODULE}.fix_method_folder", new=mocker.AsyncMock(return_value=result))
    return mock_fix


def _patch_inputs(mocker: MockerFixture) -> MockType:
    mocker.patch(f"{INPUTS_MODULE}.make_pipelex_for_agent_cli")
    mocker.patch(f"{INPUTS_MODULE}.Pipelex.teardown_if_needed")
    mocker.patch(f"{INPUTS_MODULE}.emit_inputs_result")
    mock_inputs: MockType = mocker.patch(f"{INPUTS_MODULE}.inputs_core", new=mocker.AsyncMock(return_value={"success": True}))
    return mock_inputs


class TestAgentFolderEntryCommands:
    @pytest.mark.parametrize("shape", list(MethodFolderShape))
    def test_validate_judges_the_whole_method_whatever_its_main_pipes(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        """Every bundle of the folder is judged, as the protocol's validation judges a method, so no pipe to start at is needed."""
        mocks = _patch_validate(mocker)
        write_method_folder(directory=tmp_path, shape=shape)

        validate_bundle_cmd(path=str(tmp_path))

        kwargs = mocks.folder.call_args.kwargs
        assert kwargs["method_dir"] == tmp_path
        assert kwargs["library_dirs"] == [tmp_path]
        assert kwargs["pipe_code"] is None
        mocks.whole.assert_not_called()
        mocks.sliced.assert_not_called()

    def test_validate_naming_its_pipe_narrows_the_dry_run_of_the_whole_method(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocks = _patch_validate(mocker)
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.SEVERAL_MAIN_PIPES)

        validate_bundle_cmd(path=str(tmp_path), pipe=NAMED_PIPE.pipe_ref)

        assert mocks.folder.call_args.kwargs["method_dir"] == tmp_path
        assert mocks.folder.call_args.kwargs["pipe_code"] == NAMED_PIPE.pipe_ref

    @pytest.mark.parametrize("shape", _RESOLVED_SHAPES)
    def test_validate_draws_the_pipe_the_method_starts_at(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        """The view is drawn from the method's main pipe, in the bundle defining it, which need not declare it as its own."""
        mocks = _patch_validate(mocker)
        write_method_folder(directory=tmp_path, shape=shape)
        assert shape.entry is not None

        validate_bundle_cmd(path=str(tmp_path), graph=True, view=True)

        for drawn in (mocks.graph, mocks.view):
            assert drawn.call_args.kwargs["bundle_path"] == tmp_path / shape.entry.tree_path
            assert drawn.call_args.kwargs["pipe_code"] == shape.entry.pipe_ref
        assert "graph_unavailable" not in mocks.success.call_args.args[0]

    @pytest.mark.parametrize("shape", _UNDECIDED_SHAPES)
    def test_validate_says_plainly_when_the_method_has_no_pipe_to_draw(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        """The validation stands: the result says why no graph was drawn, and the command exits 0."""
        mocks = _patch_validate(mocker)
        write_method_folder(directory=tmp_path, shape=shape)
        assert shape.refusal is not None

        validate_bundle_cmd(path=str(tmp_path), graph=True, view=True)

        mocks.graph.assert_not_called()
        mocks.view.assert_not_called()
        result = mocks.success.call_args.args[0]
        assert result["is_valid"] is True
        assert result["graph_unavailable"].startswith("No graph was drawn, since a graph is drawn from one pipe: ")
        assert shape.refusal in result["graph_unavailable"]

    @pytest.mark.parametrize("pipe", [NAMED_PIPE.pipe_ref, "second"])
    def test_validate_draws_the_pipe_named_in_the_bundle_defining_it(self, mocker: MockerFixture, tmp_path: Path, pipe: str) -> None:
        mocks = _patch_validate(mocker)
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.SEVERAL_MAIN_PIPES)

        validate_bundle_cmd(path=str(tmp_path), pipe=pipe, view=True)

        assert mocks.view.call_args.kwargs["bundle_path"] == tmp_path / NAMED_PIPE.tree_path
        assert mocks.view.call_args.kwargs["pipe_code"] == NAMED_PIPE.pipe_ref

    @pytest.mark.parametrize("shape", list(MethodFolderShape))
    def test_fix_patches_the_whole_method_validate_judges(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        mock_fix = _patch_fix(mocker)
        write_method_folder(directory=tmp_path, shape=shape)

        fix_bundle_cmd(path=str(tmp_path))

        assert mock_fix.call_args.kwargs["method_dir"] == tmp_path
        assert mock_fix.call_args.kwargs["library_dirs"] == [tmp_path]

    def test_fix_reports_a_folder_whose_tree_is_refused_as_the_still_invalid_problem(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The still-invalid problem of a fix that could not be made, `method.invalid` with the fix result beside it, never a bare refusal."""
        mock_fix = _patch_fix(mocker)
        _write_folder_with_a_refused_tree(directory=tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(tmp_path), error_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "method.invalid"
        assert problem["is_valid"] is False
        assert problem["bundle_path"] == str(tmp_path.resolve())
        assert problem["iterations"] == 0
        assert problem["fixes_applied"] == []
        assert problem["files_written"] == []
        (item,) = problem["errors"]
        # The item names the rule the tree breaks and the file at fault, the symbolic link, without quoting the refusal.
        assert item["code"] == "method.package_invalid"
        assert item["params"] == {"reason": "symbolic_link", "path": "linked.mthds"}
        assert item["location"]["file"] == "linked.mthds"

        # The Markdown lists the same item, naming the file the tree refused.
        with pytest.raises(typer.Exit):
            fix_bundle_cmd(path=str(tmp_path), error_format=CliOutputFormat.MARKDOWN)
        assert "linked.mthds" in capsys.readouterr().err
        mock_fix.assert_not_called()

    @pytest.mark.parametrize("command", ["validate", "fix", "inputs", "run"])
    def test_a_configuration_that_does_not_validate_before_the_boot_is_the_failed_boot_problem(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
    ) -> None:
        """Listing the tree reads its limits from the configuration: a refusal there is the problem a failed boot gives."""
        mocker.patch("pipelex.libraries.method_trees.local_tree_limits", side_effect=PipelexConfigError("the configuration is out of date"))
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.ONE_DECLARED_MAIN_PIPE)

        with pytest.raises(typer.Exit) as exc_info:
            _invoke_pre_boot_command(command=command, path=tmp_path)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "pipelex.config.invalid"
        assert problem["diagnostics"]["error_class"] == "PipelexConfigError"
        assert problem["message"] == "the configuration is out of date"

    @pytest.mark.parametrize("command", ["validate", "fix"])
    def test_validate_and_fix_refuse_a_folder_holding_no_bundle_with_no_verdict(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
    ) -> None:
        mocks = _patch_validate(mocker)
        mock_fix = _patch_fix(mocker)

        with pytest.raises(typer.Exit) as exc_info:
            _invoke_validate_or_fix_for_json(command=command, path=tmp_path)

        assert exc_info.value.exit_code == 2
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "method.invalid"
        assert problem["diagnostics"]["error_class"] == "EmptyMethodTreeError"
        assert problem["message"] == f"The folder '{tmp_path}' holds no .mthds bundle."
        mocks.folder.assert_not_called()
        mock_fix.assert_not_called()

    @pytest.mark.parametrize("shape", _RESOLVED_SHAPES)
    def test_inputs_is_for_the_pipe_the_method_starts_at(self, mocker: MockerFixture, tmp_path: Path, shape: MethodFolderShape) -> None:
        mock_inputs = _patch_inputs(mocker)
        write_method_folder(directory=tmp_path, shape=shape)
        assert shape.entry is not None

        inputs_bundle_cmd(path=str(tmp_path))

        kwargs = mock_inputs.call_args.kwargs
        assert kwargs["pipe_code"] == shape.entry.pipe_ref
        assert kwargs["bundle_path"] == (tmp_path / shape.entry.tree_path).resolve()
        assert kwargs["library_dirs"] == [tmp_path]

    def test_inputs_naming_its_pipe_loads_the_folder_as_its_library(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """With `--pipe`, several main pipes are no ambiguity, and the pipe is looked up in the method, as a run does."""
        mock_inputs = _patch_inputs(mocker)
        write_method_folder(directory=tmp_path, shape=MethodFolderShape.SEVERAL_MAIN_PIPES)

        inputs_bundle_cmd(path=str(tmp_path), pipe=NAMED_PIPE.pipe_ref)

        kwargs = mock_inputs.call_args.kwargs
        assert kwargs["pipe_code"] == NAMED_PIPE.pipe_ref
        assert kwargs["bundle_path"] is None
        assert kwargs["library_dirs"] == [tmp_path]

    @pytest.mark.parametrize("shape", _UNDECIDED_SHAPES)
    def test_inputs_refuses_a_folder_with_no_single_main_pipe(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str], shape: MethodFolderShape
    ) -> None:
        mock_inputs = _patch_inputs(mocker)
        write_method_folder(directory=tmp_path, shape=shape)

        with pytest.raises(typer.Exit) as exc_info:
            inputs_bundle_cmd(path=str(tmp_path))

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "request.pipe_unspecified"
        assert problem["diagnostics"]["error_class"] == "MethodEntryError"
        assert problem["message"] == _run_refusal(directory=tmp_path)
        mock_inputs.assert_not_called()
