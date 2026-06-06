"""Tests for --traceback flag in _execute_run inner exception handlers.

Verifies that print_traceback_if_requested fires inside _execute_run's
inner except blocks before typer.Exit propagates, which is the actual
scenario described in issue #437.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import click
import pytest
import typer
from rich.traceback import Traceback

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from pytest_mock import MockerFixture

from pipelex.cli.commands.run._run_core import _execute_run  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.exceptions import PipelineExecutionError

OUTPUT_DIR = "temp/test_outputs"


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestTracebackFlagInExecuteRunInnerExcepts:
    """Verify that _execute_run inner except blocks call print_traceback_if_requested."""

    def test_pipeline_execution_error_prints_traceback(self, mocker: MockerFixture) -> None:
        """PipelineExecutionError in _execute_run prints traceback when --traceback is active."""
        mock_console = mocker.MagicMock()

        exc = PipelineExecutionError(
            message="boom",
            run_mode=PipeRunMode.LIVE,
            pipe_code="test-pipe",
            output_name=None,
            pipe_stack=["test-pipe"],
        )

        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=mock_console)
        mock_runner_cls = mocker.patch("pipelex.cli.commands.run._run_core.PipelexRunner")

        mock_runner = mocker.MagicMock()
        mock_runner.execute_pipeline = mocker.MagicMock(side_effect=exc)
        mock_runner_cls.return_value = mock_runner

        # Patch get_config to provide a minimal execution config
        mock_config = mocker.MagicMock()
        mock_config.pipelex.pipeline_execution_config.with_execution_overrides.return_value = mocker.MagicMock()
        mocker.patch("pipelex.cli.commands.run._run_core.get_config", return_value=mock_config)

        ctx = click.Context(click.Command("run"), obj={"traceback": True})
        with ctx:
            try:
                raise exc
            except PipelineExecutionError:
                # Now call _execute_run which will re-raise via the runner mock
                with pytest.raises(typer.Exit):
                    _run_async(
                        _execute_run(
                            pipe_code="test-pipe",
                            bundle_path=None,
                            inputs=None,
                            save_working_memory=False,
                            working_memory_path=None,
                            save_main_stuff=False,
                            no_pretty_print=True,
                            graph=None,
                            graph_full_data=None,
                            output_dir=OUTPUT_DIR,
                            dry_run=False,
                            mock_inputs=False,
                            library_dir=None,
                        )
                    )

        # print_traceback_if_requested should have called console.print with a Traceback
        traceback_calls = [call for call in mock_console.print.call_args_list if call[0] and isinstance(call[0][0], Traceback)]
        assert len(traceback_calls) >= 1, "Expected at least one Traceback print call"

    def test_bundle_file_not_found_prints_traceback(self, mocker: MockerFixture) -> None:
        """FileNotFoundError for bundle in _execute_run prints traceback when --traceback is active."""
        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=mock_console)

        ctx = click.Context(click.Command("run"), obj={"traceback": True})
        with ctx, pytest.raises(typer.Exit):
            _run_async(
                _execute_run(
                    pipe_code=None,
                    bundle_path="/nonexistent/path/to/bundle.mthds",
                    inputs=None,
                    save_working_memory=False,
                    working_memory_path=None,
                    save_main_stuff=False,
                    no_pretty_print=True,
                    graph=None,
                    graph_full_data=None,
                    output_dir=OUTPUT_DIR,
                    dry_run=False,
                    mock_inputs=False,
                    library_dir=None,
                )
            )

        traceback_calls = [call for call in mock_console.print.call_args_list if call[0] and isinstance(call[0][0], Traceback)]
        assert len(traceback_calls) >= 1, "Expected at least one Traceback print call for bundle FileNotFoundError"

    def test_json_decode_error_prints_traceback(self, mocker: MockerFixture) -> None:
        """json.JSONDecodeError for inline inputs prints traceback when --traceback is active."""
        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=mock_console)

        ctx = click.Context(click.Command("run"), obj={"traceback": True})
        with ctx, pytest.raises(typer.Exit):
            _run_async(
                _execute_run(
                    pipe_code="test-pipe",
                    bundle_path=None,
                    inputs="{invalid json!!!",
                    save_working_memory=False,
                    working_memory_path=None,
                    save_main_stuff=False,
                    no_pretty_print=True,
                    graph=None,
                    graph_full_data=None,
                    output_dir=OUTPUT_DIR,
                    dry_run=False,
                    mock_inputs=False,
                    library_dir=None,
                )
            )

        traceback_calls = [call for call in mock_console.print.call_args_list if call[0] and isinstance(call[0][0], Traceback)]
        assert len(traceback_calls) >= 1, "Expected at least one Traceback print call for JSONDecodeError"

    def test_no_traceback_when_flag_absent(self, mocker: MockerFixture) -> None:
        """FileNotFoundError for bundle does NOT print traceback when --traceback is False."""
        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=mock_console)

        ctx = click.Context(click.Command("run"), obj={"traceback": False})
        with ctx, pytest.raises(typer.Exit):
            _run_async(
                _execute_run(
                    pipe_code=None,
                    bundle_path="/nonexistent/path/to/bundle.mthds",
                    inputs=None,
                    save_working_memory=False,
                    working_memory_path=None,
                    save_main_stuff=False,
                    no_pretty_print=True,
                    graph=None,
                    graph_full_data=None,
                    output_dir=OUTPUT_DIR,
                    dry_run=False,
                    mock_inputs=False,
                    library_dir=None,
                )
            )

        # No Traceback should have been printed
        for call in mock_console.print.call_args_list:
            args = call[0]
            for arg in args:
                assert not isinstance(arg, Traceback), "Traceback should NOT be printed when flag is absent"
