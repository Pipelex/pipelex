"""Tests for print_traceback_if_requested().

Verifies that the function prints a Rich traceback only when --traceback is active.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from rich.traceback import Traceback

from pipelex.cli.error_handlers import print_traceback_if_requested

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestPrintTracebackIfRequested:
    """Unit tests for print_traceback_if_requested()."""

    def test_does_not_print_when_flag_not_set(self, mocker: MockerFixture) -> None:
        """When --traceback is not active, console.print should not be called."""
        console = mocker.MagicMock()
        ctx = click.Context(click.Command("test"), obj={"traceback": False})
        with ctx:
            print_traceback_if_requested(console=console)
        console.print.assert_not_called()

    def test_prints_traceback_when_flag_set(self, mocker: MockerFixture) -> None:
        """When --traceback is active, console.print should be called with a Traceback."""
        console = mocker.MagicMock()
        ctx = click.Context(click.Command("test"), obj={"traceback": True})
        with ctx:
            try:
                msg = "test error"
                raise ValueError(msg)
            except ValueError:
                print_traceback_if_requested(console=console)
        console.print.assert_called_once()
        arg = console.print.call_args[0][0]
        assert isinstance(arg, Traceback)
