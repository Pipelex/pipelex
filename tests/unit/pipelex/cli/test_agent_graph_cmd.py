"""Unit tests for the agent CLI graph command."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.graph_cmd import graph_cmd
from pipelex.core.interpreter.exceptions import MthdsDecodeError
from pipelex.graph.graph_rendering import GraphFormat
from pipelex.tools.misc.chart_utils import FlowchartDirection

GRAPH_CMD_MODULE = "pipelex.cli.agent_cli.commands.graph_cmd"


class TestGraphCmd:
    """Tests for the graph command that generates HTML from a .mthds bundle."""

    def _mock_blueprint(self, mocker: MockerFixture, *, main_pipe: str = "my_pipe") -> None:
        """Mock bundle parsing to return a blueprint with the given main_pipe."""
        mock_blueprint = mocker.MagicMock()
        mock_blueprint.main_pipe = main_pipe
        mocker.patch(
            f"{GRAPH_CMD_MODULE}.PipelexInterpreter.make_pipelex_bundle_blueprint",
            return_value=mock_blueprint,
        )

    def _mock_execution(self, mocker: MockerFixture, *, graph_spec_present: bool = True) -> None:
        """Mock the Pipelex init, execute_pipeline, render_graph_from_spec, and teardown."""
        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")

        mock_config = mocker.MagicMock()
        mocker.patch(f"{GRAPH_CMD_MODULE}.get_config", return_value=mock_config)

        mock_pipe_output = mocker.MagicMock()
        if graph_spec_present:
            mock_pipe_output.graph_spec = mocker.MagicMock()
        else:
            mock_pipe_output.graph_spec = None

        saved_files = {"reactflow_html": Path("graph/reactflow.html")}

        # Patch async functions with non-async mocks so no coroutines are created (avoids "coroutine never awaited" warnings)
        mocker.patch(f"{GRAPH_CMD_MODULE}.execute_pipeline", new=mocker.MagicMock())
        mocker.patch(f"{GRAPH_CMD_MODULE}.render_graph_from_spec", new=mocker.MagicMock())

        # asyncio.run is called twice: first for execute_pipeline, then for render_graph_from_spec
        mocker.patch(f"{GRAPH_CMD_MODULE}.asyncio.run", side_effect=[mock_pipe_output, saved_files])

    def test_valid_mthds_file_produces_success_json(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Valid .mthds file should produce success JSON with pipe_code and output_dir."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_blueprint(mocker)
        self._mock_execution(mocker)

        graph_cmd(target=str(mthds_file))

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["pipe_code"] == "my_pipe"
        assert "output_dir" in parsed
        assert "files" in parsed

    def test_valid_mthds_file_calls_asyncio_run_twice(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Valid .mthds file should call asyncio.run twice (execute_pipeline + render_graph_from_spec)."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_blueprint(mocker)

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD_MODULE}.get_config")

        # Patch async functions with non-async mocks so no coroutines are created (avoids "coroutine never awaited" warnings)
        mocker.patch(f"{GRAPH_CMD_MODULE}.execute_pipeline", new=mocker.MagicMock())
        mocker.patch(f"{GRAPH_CMD_MODULE}.render_graph_from_spec", new=mocker.MagicMock())

        mock_pipe_output = mocker.MagicMock()
        mock_pipe_output.graph_spec = mocker.MagicMock()
        saved_files = {"reactflow_html": Path("graph/reactflow.html")}
        mock_asyncio_run = mocker.patch(
            f"{GRAPH_CMD_MODULE}.asyncio.run",
            side_effect=[mock_pipe_output, saved_files],
        )

        graph_cmd(target=str(mthds_file))

        assert mock_asyncio_run.call_count == 2

    def test_non_mthds_file_produces_error(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Non-MTHDS file (e.g. .json, .txt) should produce an ArgumentError."""
        json_file = tmp_path / "graphspec.json"
        json_file.write_text("{}")

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(target=str(json_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "ArgumentError"
        assert ".mthds" in parsed["message"]

    def test_file_not_found_produces_error(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Missing file should produce a FileNotFoundError."""
        missing = tmp_path / "nonexistent.mthds"

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(target=str(missing))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "FileNotFoundError"

    def test_bundle_without_main_pipe_produces_error(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Bundle that doesn't declare main_pipe should produce a BundleError."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[domain]\ncode = "test"')

        mock_blueprint = mocker.MagicMock()
        mock_blueprint.main_pipe = None
        mocker.patch(
            f"{GRAPH_CMD_MODULE}.PipelexInterpreter.make_pipelex_bundle_blueprint",
            return_value=mock_blueprint,
        )

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(target=str(mthds_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "BundleError"
        assert "main_pipe" in parsed["message"]

    def test_no_graph_spec_produces_error(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """If pipe_output.graph_spec is None, should produce a GraphSpecMissingError."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_blueprint(mocker)

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD_MODULE}.get_config")

        # Patch async function with non-async mock so no coroutine is created (avoids "coroutine never awaited" warning)
        mocker.patch(f"{GRAPH_CMD_MODULE}.execute_pipeline", new=mocker.MagicMock())

        mock_pipe_output = mocker.MagicMock()
        mock_pipe_output.graph_spec = None
        mocker.patch(f"{GRAPH_CMD_MODULE}.asyncio.run", return_value=mock_pipe_output)

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(target=str(mthds_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "GraphSpecMissingError"

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
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        format_option: GraphFormat,
    ) -> None:
        """Each format option should produce success JSON."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_blueprint(mocker)
        self._mock_execution(mocker)

        graph_cmd(target=str(mthds_file), graph_format=format_option)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True

    def test_default_format_is_reactflow(self) -> None:
        """Default graph format should be REACTFLOW."""
        sig = inspect.signature(graph_cmd)
        default = sig.parameters["graph_format"].default
        assert default == GraphFormat.REACTFLOW

    def test_direction_forwarded_to_render_graph_from_spec(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Direction option should be forwarded to render_graph_from_spec via asyncio.run."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        self._mock_blueprint(mocker)

        mocker.patch(f"{GRAPH_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{GRAPH_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD_MODULE}.get_config")

        mock_execute = mocker.MagicMock()
        mock_render = mocker.MagicMock()
        mocker.patch(f"{GRAPH_CMD_MODULE}.execute_pipeline", new=mock_execute)
        mocker.patch(f"{GRAPH_CMD_MODULE}.render_graph_from_spec", new=mock_render)

        mock_pipe_output = mocker.MagicMock()
        mock_pipe_output.graph_spec = mocker.MagicMock()
        saved_files = {"reactflow_html": Path("graph/reactflow.html")}
        mocker.patch(
            f"{GRAPH_CMD_MODULE}.asyncio.run",
            side_effect=[mock_pipe_output, saved_files],
        )

        graph_cmd(target=str(mthds_file), direction=FlowchartDirection.LEFT_TO_RIGHT)

        # Verify direction was forwarded to render_graph_from_spec
        mock_render.assert_called_once()
        _, render_kwargs = mock_render.call_args
        assert render_kwargs["direction"] == FlowchartDirection.LEFT_TO_RIGHT

    def test_mthds_parse_error_produces_error(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """MTHDS parse error should produce a MthdsDecodeError."""
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text("invalid toml {{{{")

        mocker.patch(
            f"{GRAPH_CMD_MODULE}.PipelexInterpreter.make_pipelex_bundle_blueprint",
            side_effect=MthdsDecodeError(message="bad toml", doc="invalid toml {{{{", pos=0, lineno=1, colno=1),
        )

        with pytest.raises(typer.Exit) as exc_info:
            graph_cmd(target=str(mthds_file))

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "MthdsDecodeError"
