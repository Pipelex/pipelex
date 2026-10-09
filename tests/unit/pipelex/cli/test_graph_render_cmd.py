"""`pipelex graph render` when rendering fails: on a spec this version refuses, the diagnosis names the file exactly as
the user wrote it, and on an unexpected error the log line carries the error as fields while the console prints its
traceback without the locals.

Boot, teardown and telemetry are mocked out so no real Pipelex is made; the console is swapped for one
writing to a buffer so the printed diagnosis can be read back.
"""

from __future__ import annotations

import contextlib
import io
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.graph_cmd import graph_render_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

GRAPH_CMD = "pipelex.cli.commands.graph_cmd"


class TestGraphRenderFailure:
    @pytest.mark.parametrize("bracketed_dir", ["[draft]", "[/old]"])
    def test_a_bracketed_path_prints_as_written(self, mocker: MockerFixture, tmp_path: Path, bracketed_dir: str) -> None:
        """A path is the user's text, not Rich markup: `[draft]` used to be swallowed as a style tag, naming a
        file that does not exist, and `[/old]` raised a `MarkupError` in place of the diagnosis.
        """
        mocker.patch(f"{GRAPH_CMD}.make_pipelex_for_cli")
        mocker.patch(f"{GRAPH_CMD}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD}.tag")
        telemetry_manager = mocker.patch(f"{GRAPH_CMD}.get_telemetry_manager").return_value
        telemetry_manager.telemetry_context.return_value = contextlib.nullcontext()
        printed = io.StringIO()
        mocker.patch(f"{GRAPH_CMD}.get_console", return_value=Console(file=printed, width=1000))
        log_spy = mocker.patch(f"{GRAPH_CMD}.log")

        spec_dir = tmp_path / bracketed_dir
        spec_dir.mkdir(parents=True)
        spec_file = spec_dir / "graph.json"
        spec_file.write_text("{}", encoding="utf-8")

        with pytest.raises(typer.Exit) as exit_info:
            graph_render_cmd(input_file=spec_file)

        assert exit_info.value.exit_code == 1
        assert "Failed to render graph" in printed.getvalue()
        assert str(spec_file) in printed.getvalue()
        # The log line is a fixed message and carries the path and the diagnosis as written, with no escape:
        # only the console print reads markup, and no sink reads a log message as markup.
        log_spy.error.assert_called_once()
        assert log_spy.error.call_args.args == ("The graph spec was refused, so no graph was rendered",)
        fields = log_spy.error.call_args.kwargs["fields"]
        assert fields["file.path"] == str(spec_file)
        assert fields["error.type"] == "GraphSpecValidationError"
        assert str(spec_file) in fields["error.message"]
        assert "\\[" not in fields["error.message"]

    def test_an_unexpected_error_logs_its_fields_and_prints_no_locals(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The log line is a fixed message with the error's class and text, and carries no exception, whose chain can quote
        the graph file's traced content; the console's traceback prints no locals, which would print the loaded graph.
        """
        mocker.patch(f"{GRAPH_CMD}.make_pipelex_for_cli")
        mocker.patch(f"{GRAPH_CMD}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD}.tag")
        telemetry_manager = mocker.patch(f"{GRAPH_CMD}.get_telemetry_manager").return_value
        telemetry_manager.telemetry_context.return_value = contextlib.nullcontext()
        printed = io.StringIO()
        mocker.patch(f"{GRAPH_CMD}.get_console", return_value=Console(file=printed, width=1000))
        mocker.patch(f"{GRAPH_CMD}._do_graph_render", side_effect=RuntimeError("the renderer broke"))
        log_spy = mocker.patch(f"{GRAPH_CMD}.log")

        spec_file = tmp_path / "graph.json"
        spec_file.write_text("{}", encoding="utf-8")

        with pytest.raises(typer.Exit) as exit_info:
            graph_render_cmd(input_file=spec_file)

        assert exit_info.value.exit_code == 1
        assert "Failed to render graph" in printed.getvalue()
        assert "the renderer broke" in printed.getvalue()
        assert " locals ─" not in printed.getvalue()
        log_spy.error.assert_called_once_with(
            "The graph could not be rendered",
            fields={"file.path": str(spec_file), "error.type": "RuntimeError", "error.message": "the renderer broke"},
        )
