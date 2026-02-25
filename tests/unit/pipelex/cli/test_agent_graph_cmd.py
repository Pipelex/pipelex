"""Unit tests for the agent CLI graph command."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.graph_cmd import graph_cmd
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.graph.graph_rendering import GraphFormat, generate_graph_for_bundle
from pipelex.tools.misc.chart_utils import FlowchartDirection

GRAPH_CMD_MODULE = "pipelex.cli.agent_cli.commands.graph_cmd"
GRAPH_RENDERING_MODULE = "pipelex.graph.graph_rendering"


class TestGraphCmd:
    """Tests for the graph command that generates HTML from a .mthds bundle."""

    def _mock_generate_graph_for_bundle(
        self,
        mocker: MockerFixture,
        *,
        pipe_code: str = "my_pipe",
        output_dir: str = "mock_output",
        direction: str | None = None,
    ) -> Any:
        """Mock generate_graph_for_bundle to return a successful result dict."""
        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")

        result = {
            "graph_files": {"reactflow_html": "graph/reactflow.html"},
            "graph_output_dir": output_dir,
            "pipe_code": pipe_code,
            "direction": direction,
        }
        return mocker.patch(
            f"{GRAPH_CMD_MODULE}.generate_graph_for_bundle",
            new=mocker.AsyncMock(return_value=result),
        )

    def test_valid_mthds_file_produces_success_json(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Valid .mthds file should produce success JSON with pipe_code and output_dir."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_generate_graph_for_bundle(mocker, output_dir=str(tmp_path))

        graph_cmd(ctx=agent_ctx, target=str(mthds_file))

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["pipe_code"] == "my_pipe"
        assert "output_dir" in parsed
        assert "files" in parsed

    def test_valid_mthds_file_calls_generate_graph_once(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Valid .mthds file should call generate_graph_for_bundle once."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        mock_generate = self._mock_generate_graph_for_bundle(mocker)

        graph_cmd(ctx=agent_ctx, target=str(mthds_file))

        assert mock_generate.call_count == 1

    def test_non_mthds_file_produces_error(
        self,
        agent_ctx: Any,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Non-MTHDS file (e.g. .json, .txt) should produce an ArgumentError."""
        json_file = tmp_path / "graphspec.json"
        json_file.write_text("{}")

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(ctx=agent_ctx, target=str(json_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "ArgumentError"
        assert ".mthds" in parsed["message"]

    def test_file_not_found_produces_error(
        self,
        agent_ctx: Any,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Missing file should produce a FileNotFoundError."""
        missing = tmp_path / "nonexistent.mthds"

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(ctx=agent_ctx, target=str(missing))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "FileNotFoundError"

    def test_bundle_without_main_pipe_produces_error(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Bundle that doesn't declare main_pipe should produce a PipelexInterpreterError."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[domain]\ncode = "test"')

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(
            f"{GRAPH_CMD_MODULE}.generate_graph_for_bundle",
            new=mocker.AsyncMock(side_effect=PipelexInterpreterError("does not declare a main_pipe")),
        )

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(ctx=agent_ctx, target=str(mthds_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "PipelexInterpreterError"
        assert "main_pipe" in parsed["message"]

    def test_no_graph_spec_produces_error(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """If pipeline execution does not produce a graph spec, should produce an error."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(
            f"{GRAPH_CMD_MODULE}.generate_graph_for_bundle",
            new=mocker.AsyncMock(side_effect=PipelexError("Pipeline execution did not produce a graph spec")),
        )

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(ctx=agent_ctx, target=str(mthds_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert "graph spec" in parsed["message"].lower()

    @pytest.mark.parametrize(
        "format_option",
        [
            GraphFormat.REACTFLOW,
            GraphFormat.MERMAIDFLOW,
            GraphFormat.BOTH,
        ],
    )
    def test_format_option_produces_success(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        format_option: GraphFormat,
    ) -> None:
        """Each format option should produce success JSON."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_generate_graph_for_bundle(mocker)

        graph_cmd(ctx=agent_ctx, target=str(mthds_file), graph_format=format_option)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True

    def test_default_format_is_reactflow(self) -> None:
        """Default graph format should be REACTFLOW."""
        sig = inspect.signature(graph_cmd)
        default = sig.parameters["graph_format"].default
        assert default == GraphFormat.REACTFLOW

    def test_direction_forwarded_to_generate_graph_for_bundle(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Direction option should be forwarded to generate_graph_for_bundle."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")

        result = {
            "graph_files": {"reactflow_html": "graph/reactflow.html"},
            "graph_output_dir": "mock_output",
            "pipe_code": "my_pipe",
            "direction": "left_to_right",
        }
        mock_generate = mocker.patch(
            f"{GRAPH_CMD_MODULE}.generate_graph_for_bundle",
            new=mocker.AsyncMock(return_value=result),
        )

        graph_cmd(ctx=agent_ctx, target=str(mthds_file), direction=FlowchartDirection.LEFT_TO_RIGHT)

        # Verify generate_graph_for_bundle was called with the correct direction
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args
        assert call_kwargs.kwargs.get("direction") == FlowchartDirection.LEFT_TO_RIGHT

    def test_mthds_parse_error_produces_error(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """MTHDS parse error should produce a MthdsDecodeError."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text("invalid toml {{{{")

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(
            f"{GRAPH_CMD_MODULE}.generate_graph_for_bundle",
            new=mocker.AsyncMock(side_effect=MthdsDecodeError(message="bad toml", doc="invalid toml {{{{", pos=0, lineno=1, colno=1)),
        )

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(ctx=agent_ctx, target=str(mthds_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "MthdsDecodeError"

    def test_bundle_parent_dir_included_in_library_dirs(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """generate_graph_for_bundle should include the bundle's parent dir in library_dirs.

        This verifies the bug fix: when no --library-dir is passed, the bundle's
        parent directory must still be included so PipelexRunner can resolve
        sibling dependencies.
        """
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        mock_blueprint = mocker.MagicMock()
        mock_blueprint.main_pipe = "my_pipe"
        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.PipelexInterpreter.make_pipelex_bundle_blueprint",
            return_value=mock_blueprint,
        )

        mock_config = mocker.MagicMock()
        mocker.patch(f"{GRAPH_RENDERING_MODULE}.get_config", return_value=mock_config)

        mock_runner_cls = mocker.patch(f"{GRAPH_RENDERING_MODULE}.PipelexRunner")
        mock_runner_instance = mocker.MagicMock()
        mock_pipe_output = mocker.MagicMock()
        mock_pipe_output.graph_spec = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.pipe_output = mock_pipe_output
        mock_runner_instance.execute_pipeline = mocker.AsyncMock(return_value=mock_response)
        mock_runner_cls.return_value = mock_runner_instance

        mocker.patch(
            f"{GRAPH_RENDERING_MODULE}.render_graph_from_spec",
            new=mocker.AsyncMock(return_value={"reactflow_html": Path("graph/reactflow.html")}),
        )

        asyncio.run(
            generate_graph_for_bundle(
                bundle_path=mthds_file,
                graph_format=GraphFormat.REACTFLOW,
                library_dirs=None,
                direction=None,
            )
        )

        # Verify PipelexRunner was constructed with library_dirs containing the bundle's parent dir
        mock_runner_cls.assert_called_once()
        call_kwargs = mock_runner_cls.call_args
        actual_library_dirs = call_kwargs.kwargs.get("library_dirs") or call_kwargs[1].get("library_dirs")
        bundle_parent = str(tmp_path.resolve())
        assert actual_library_dirs is not None, "library_dirs should not be None"
        assert bundle_parent in actual_library_dirs, f"Bundle parent dir '{bundle_parent}' should be in library_dirs, got: {actual_library_dirs}"
