"""Integration tests for error handlers respecting the --traceback flag.

Verifies that a handler (here handle_model_deck_preset_error) prints or omits a Rich
traceback depending on the --traceback flag state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
import pytest
import typer
from rich.traceback import Traceback

from pipelex.cli.error_handlers import ErrorContext, handle_model_deck_preset_error
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.cogt.model_backends.model_type import ModelType

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _deck_preset_error() -> ModelDeckPresetValidatonError:
    return ModelDeckPresetValidatonError(
        message="preset references unavailable model",
        model_type=ModelType.LLM,
        preset_id="default",
        model_handle="gpt-5",
        enabled_backends={"openai"},
    )


class TestTracebackFlagInErrorHandlers:
    """Integration: error handlers respect the --traceback flag."""

    def test_handler_prints_traceback_when_flag_active(self, mocker: MockerFixture) -> None:
        """handle_model_deck_preset_error prints traceback when --traceback is set."""
        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=mock_console)

        exc = _deck_preset_error()
        ctx = click.Context(click.Command("test"), obj={"traceback": True})
        with ctx:
            try:
                raise exc
            except ModelDeckPresetValidatonError:
                with pytest.raises(typer.Exit):
                    handle_model_deck_preset_error(exc, context=ErrorContext.VALIDATION)

        # The first call to console.print should be the Traceback
        first_call_arg = mock_console.print.call_args_list[0][0][0]
        assert isinstance(first_call_arg, Traceback)

    def test_handler_does_not_print_traceback_when_flag_absent(self, mocker: MockerFixture) -> None:
        """handle_model_deck_preset_error does NOT print traceback without --traceback."""
        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=mock_console)

        exc = _deck_preset_error()
        ctx = click.Context(click.Command("test"), obj={"traceback": False})
        with ctx:
            try:
                raise exc
            except ModelDeckPresetValidatonError:
                with pytest.raises(typer.Exit):
                    handle_model_deck_preset_error(exc, context=ErrorContext.VALIDATION)

        # No call should have a Traceback argument
        for call in mock_console.print.call_args_list:
            args = call[0]
            for arg in args:
                assert not isinstance(arg, Traceback)
