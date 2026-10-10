"""`pipelex graph render` when rendering fails: on a spec this version refuses, the diagnosis names the file exactly as
the user wrote it, and on an unexpected error the log line carries the exception, whose traceback every sink writes its
own way, while the console names the exception's type and message and prints no traceback of its own.

Boot, teardown and telemetry are mocked out so no real Pipelex is made; the console is swapped for one
writing to a buffer so the printed diagnosis can be read back.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.graph_cmd import graph_render_cmd
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from tests.helpers.console_log_rendering import console_sink_on_buffer, installed_log

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from pipelex.tools.log.log_sink import LogSink

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

    def test_an_unexpected_error_logs_its_traceback_once(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The log line is a fixed message with the file, and carries the exception for every sink to write its traceback,
        the console under the line; the console prints no traceback of its own, which would show it twice.
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
        assert "RuntimeError: the renderer broke" in printed.getvalue()
        assert "Traceback" not in printed.getvalue()
        log_spy.error.assert_called_once_with("The graph could not be rendered", fields={"file.path": str(spec_file)}, include_exception=True)

    @pytest.mark.parametrize("sink_kind", ["console", "json"])
    def test_an_unexpected_error_names_its_cause_on_the_terminal_whatever_the_sink(
        self, mocker: MockerFixture, tmp_path: Path, caplog: pytest.LogCaptureFixture, sink_kind: str
    ) -> None:
        """Under a sink that does not write to the terminal, the CLI's own output was "Failed to render graph" and nothing else.

        The CLI names the exception's type and message itself, and the traceback is printed once, by the log line.
        """
        caplog.set_level(logging.INFO, logger=GRAPH_CMD)
        mocker.patch(f"{GRAPH_CMD}.make_pipelex_for_cli")
        mocker.patch(f"{GRAPH_CMD}.Pipelex.teardown_if_needed")
        mocker.patch(f"{GRAPH_CMD}.tag")
        telemetry_manager = mocker.patch(f"{GRAPH_CMD}.get_telemetry_manager").return_value
        telemetry_manager.telemetry_context.return_value = contextlib.nullcontext()
        printed = io.StringIO()
        mocker.patch(f"{GRAPH_CMD}.get_console", return_value=Console(file=printed, width=1000))
        mocker.patch(f"{GRAPH_CMD}._do_graph_render", side_effect=RuntimeError("the renderer broke"))
        sink_buffer = io.StringIO()
        sink: LogSink = console_sink_on_buffer(buffer=sink_buffer) if sink_kind == "console" else JsonLogSink(stream=sink_buffer)
        spec_file = tmp_path / "graph.json"
        spec_file.write_text("{}", encoding="utf-8")

        with installed_log(sink=sink) as fresh:
            mocker.patch(f"{GRAPH_CMD}.log", new=fresh)
            with pytest.raises(typer.Exit):
                graph_render_cmd(input_file=spec_file)

        terminal = printed.getvalue()
        assert "Failed to render graph" in terminal
        assert "RuntimeError: the renderer broke" in terminal
        assert "Traceback" not in terminal
        logged = sink_buffer.getvalue()
        if sink_kind == "console":
            assert "The graph could not be rendered" in logged
            assert logged.count("Traceback") == 1
        else:
            (record,) = [json.loads(line) for line in logged.splitlines() if line and json.loads(line)[LOGGER_KEY] == GRAPH_CMD]
            assert record[MESSAGE_KEY] == "The graph could not be rendered"
            assert record[EXCEPTION_KEY].startswith("Traceback")
            assert record[EXCEPTION_KEY].rstrip().endswith("RuntimeError: the renderer broke")
