"""Tests for the --traceback global CLI flag.

Verifies that:
- Without --traceback, error handlers do NOT print a Rich traceback.
- With --traceback, error handlers print a Rich traceback before the nice panel.
- The flag is correctly intercepted by PipelexCLI.make_context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import click
import pytest
import typer
from rich.traceback import Traceback

from pipelex.cli._cli import PipelexCLI  # noqa: PLC2701
from pipelex.cli.error_handlers import (
    handle_inference_setup_required_error,
    is_traceback_requested,
    print_traceback_if_requested,
)
from pipelex.system.pipelex_service.exceptions import InferenceSetupRequiredError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestIsTracebackRequested:
    """Unit tests for is_traceback_requested()."""

    def test_returns_false_when_no_click_context(self) -> None:
        """Outside a Click context, should return False."""
        assert is_traceback_requested() is False

    def test_returns_false_when_flag_not_set(self) -> None:
        """When ctx.obj has no 'traceback' key, should return False."""
        ctx = click.Context(click.Command("test"), obj={})
        with ctx:
            assert is_traceback_requested() is False

    def test_returns_true_when_flag_set(self) -> None:
        """When ctx.obj['traceback'] is True, should return True."""
        ctx = click.Context(click.Command("test"), obj={"traceback": True})
        with ctx:
            assert is_traceback_requested() is True

    def test_returns_false_when_flag_explicitly_false(self) -> None:
        """When ctx.obj['traceback'] is False, should return False."""
        ctx = click.Context(click.Command("test"), obj={"traceback": False})
        with ctx:
            assert is_traceback_requested() is False


class TestPrintTracebackIfRequested:
    """Unit tests for print_traceback_if_requested()."""

    def test_does_not_print_when_flag_not_set(self) -> None:
        """When --traceback is not active, console.print should not be called."""
        console = MagicMock()
        ctx = click.Context(click.Command("test"), obj={"traceback": False})
        with ctx:
            print_traceback_if_requested(console)
        console.print.assert_not_called()

    def test_prints_traceback_when_flag_set(self) -> None:
        """When --traceback is active, console.print should be called with a Traceback."""
        console = MagicMock()
        ctx = click.Context(click.Command("test"), obj={"traceback": True})
        with ctx:
            try:
                msg = "test error"
                raise ValueError(msg)
            except ValueError:
                print_traceback_if_requested(console)
        console.print.assert_called_once()
        arg = console.print.call_args[0][0]
        assert isinstance(arg, Traceback)


class TestTracebackFlagInErrorHandlers:
    """Integration: error handlers respect the --traceback flag."""

    def test_handler_prints_traceback_when_flag_active(self, mocker: MockerFixture) -> None:
        """handle_inference_setup_required_error prints traceback when --traceback is set."""
        mock_console = MagicMock()
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=mock_console)

        exc = InferenceSetupRequiredError()
        ctx = click.Context(click.Command("test"), obj={"traceback": True})
        with ctx:
            try:
                raise exc
            except InferenceSetupRequiredError:
                with pytest.raises(typer.Exit):
                    handle_inference_setup_required_error(exc)

        # The first call to console.print should be the Traceback
        first_call_arg = mock_console.print.call_args_list[0][0][0]
        assert isinstance(first_call_arg, Traceback)

    def test_handler_does_not_print_traceback_when_flag_absent(self, mocker: MockerFixture) -> None:
        """handle_inference_setup_required_error does NOT print traceback without --traceback."""
        mock_console = MagicMock()
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=mock_console)

        exc = InferenceSetupRequiredError()
        ctx = click.Context(click.Command("test"), obj={"traceback": False})
        with ctx:
            try:
                raise exc
            except InferenceSetupRequiredError:
                with pytest.raises(typer.Exit):
                    handle_inference_setup_required_error(exc)

        # No call should have a Traceback argument
        for call in mock_console.print.call_args_list:
            args = call[0]
            for arg in args:
                assert not isinstance(arg, Traceback)


class TestPipelexCLIMakeContext:
    """Test that PipelexCLI.make_context intercepts --traceback."""

    def test_traceback_flag_intercepted(self) -> None:
        """--traceback should be removed from args and stored in ctx.obj."""
        group = PipelexCLI(name="pipelex")
        group.add_command(click.Command("dummy"))

        ctx = group.make_context("pipelex", ["--traceback", "dummy"])
        assert ctx.obj["traceback"] is True

    def test_no_traceback_flag(self) -> None:
        """Without --traceback, ctx.obj['traceback'] should be False."""
        group = PipelexCLI(name="pipelex")
        group.add_command(click.Command("dummy"))

        ctx = group.make_context("pipelex", ["dummy"])
        assert ctx.obj["traceback"] is False
