"""Snapshot tests for the Rich CLI error panels.

Pin the exact plain-text layout produced by the shared ``display_error_panel``
helper, guarding the Phase 7 panel refactor against rendering drift. These are
not load-bearing for production correctness — they protect the refactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pytest
import typer
from rich.console import Console

from pipelex.cli.error_handlers import ErrorContext, handle_model_availability_error, handle_model_choice_error
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

EXPECTED_MODEL_CHOICE_PANEL = (
    "\n"
    "❌ Pipe run failed because of a model choice could not be interpreted correctly\n"
    "\n"
    "Pipe:         'my_pipe' (llm_text)\n"
    "Model Type:   'llm'\n"
    "Model Choice: 'gpt-5'\n"
    "\n"
    "Error: model 'gpt-5' not found\n"
    "\n"
    "💡 Tip: Check your model configuration in .pipelex/inference/ or specify a \n"
    "different model in the 'my_pipe' pipe.\n"
    "Learn more about the inference backend system: \n"
    "https://docs.pipelex.com/latest/setup/configure-ai-providers/\n"
    "Join our Discord for help: https://go.pipelex.com/discord\n"
    "\n"
)

EXPECTED_MODEL_AVAILABILITY_PANEL = (
    "\n"
    "❌ Pipe run failed because a model wasn't available\n"
    "\n"
    "Pipe:       'my_pipe' (llm_text)\n"
    "Model:      'gpt-4o'\n"
    "Fallbacks:  gpt-4o-mini\n"
    "Pipe Stack: top_pipe → my_pipe\n"
    "\n"
    "Error: model not available\n"
    "\n"
    "💡 Tip: Check your model configuration in .pipelex/inference/ or specify a \n"
    "different model in the 'my_pipe' pipe.\n"
    "Learn more about the inference backend system: \n"
    "https://docs.pipelex.com/latest/setup/configure-ai-providers/\n"
    "Join our Discord for help: https://go.pipelex.com/discord\n"
    "\n"
)


class TestErrorHandlersSnapshot:
    """The shared panel helper renders each handler to a stable layout."""

    def _render(self, mocker: MockerFixture, render: Callable[[], None]) -> str:
        """Render a handler to plain text via a fixed-width, color-free Rich console."""
        console = Console(width=80, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=console)
        with pytest.raises(typer.Exit) as exit_info:
            render()
        assert exit_info.value.exit_code == 1
        return console.export_text()

    def test_model_choice_error_panel_snapshot(self, mocker: MockerFixture) -> None:
        """handle_model_choice_error renders the canonical panel with aligned fields."""
        exc = PipeOperatorModelChoiceError(
            message="model 'gpt-5' not found",
            pipe_type="llm_text",
            pipe_code="my_pipe",
            model_type=ModelType.LLM,
            model_choice="gpt-5",
        )
        output = self._render(mocker, lambda: handle_model_choice_error(exc, context=ErrorContext.PIPE_RUN))
        assert output == EXPECTED_MODEL_CHOICE_PANEL

    def test_model_availability_error_panel_snapshot(self, mocker: MockerFixture) -> None:
        """handle_model_availability_error renders the panel with its conditional fields."""
        exc = PipeOperatorModelAvailabilityError(
            message="model not available",
            run_mode=PipeRunMode.LIVE,
            pipe_type="llm_text",
            pipe_code="my_pipe",
            pipe_stack=["top_pipe", "my_pipe"],
            model_handle="gpt-4o",
            fallback_list=["gpt-4o-mini"],
        )
        output = self._render(mocker, lambda: handle_model_availability_error(exc, context=ErrorContext.PIPE_RUN))
        assert output == EXPECTED_MODEL_AVAILABILITY_PANEL
