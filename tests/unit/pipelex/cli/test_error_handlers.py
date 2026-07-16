"""Unit tests for the main CLI error handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_inference_setup_required_error,
    handle_model_availability_error,
    handle_model_choice_error,
    handle_model_deck_preset_error,
    handle_validate_bundle_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.pipelex_service.exceptions import InferenceSetupRequiredError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestErrorHandlers:
    """Tests for Rich error handler functions."""

    def test_handle_model_choice_error_exits_and_calls_to_error_report(self, mocker: MockerFixture) -> None:
        """handle_model_choice_error should call to_error_report() and exit with code 1."""
        mocker.patch("pipelex.cli.error_handlers.get_console")
        exc = PipeOperatorModelChoiceError(
            message="model 'gpt-5' not found",
            pipe_type="llm_text",
            pipe_code="my_pipe",
            model_type=ModelType.LLM,
            model_choice="gpt-5",
        )
        spy = mocker.spy(exc, "to_error_report")

        with pytest.raises(typer.Exit) as exc_info:
            handle_model_choice_error(exc, context=ErrorContext.PIPE_RUN)

        assert exc_info.value.exit_code == 1
        spy.assert_called_once()

    def test_handle_model_availability_error_exits_and_calls_to_error_report(self, mocker: MockerFixture) -> None:
        """handle_model_availability_error should call to_error_report() and exit with code 1."""
        mocker.patch("pipelex.cli.error_handlers.get_console")
        exc = PipeOperatorModelAvailabilityError(
            message="model not available",
            run_mode=PipeRunMode.LIVE,
            pipe_type="llm_text",
            pipe_code="my_pipe",
            pipe_stack=["my_pipe"],
            model_handle="gpt-4o",
            fallback_list=["gpt-4o-mini"],
        )
        spy = mocker.spy(exc, "to_error_report")

        with pytest.raises(typer.Exit) as exc_info:
            handle_model_availability_error(exc, context=ErrorContext.PIPE_RUN)

        assert exc_info.value.exit_code == 1
        spy.assert_called_once()

    def test_handle_model_deck_preset_error_exits_and_calls_to_error_report(self, mocker: MockerFixture) -> None:
        """handle_model_deck_preset_error should call to_error_report() and exit with code 1."""
        mocker.patch("pipelex.cli.error_handlers.get_console")
        exc = ModelDeckPresetValidatonError(
            message="preset references unavailable model",
            model_type=ModelType.LLM,
            preset_id="default",
            model_handle="gpt-5",
            enabled_backends={"openai"},
        )
        spy = mocker.spy(exc, "to_error_report")

        with pytest.raises(typer.Exit) as exc_info:
            handle_model_deck_preset_error(exc, context=ErrorContext.VALIDATION)

        assert exc_info.value.exit_code == 1
        spy.assert_called_once()

    def test_handle_validate_bundle_error_exits_and_calls_to_error_report(self, mocker: MockerFixture) -> None:
        """handle_validate_bundle_error should call to_error_report() and exit with code 1."""
        mocker.patch("pipelex.cli.error_handlers.get_console")
        exc = ValidateBundleError(message="validation failed")
        spy = mocker.spy(exc, "to_error_report")

        with pytest.raises(typer.Exit) as exc_info:
            handle_validate_bundle_error(exc)

        assert exc_info.value.exit_code == 1
        spy.assert_called_once()

    def test_handle_inference_setup_required_error_exits(self, mocker: MockerFixture) -> None:
        """handle_inference_setup_required_error should exit with code 1."""
        mocker.patch("pipelex.cli.error_handlers.get_console")
        exc = InferenceSetupRequiredError()

        with pytest.raises(typer.Exit) as exc_info:
            handle_inference_setup_required_error(exc)

        assert exc_info.value.exit_code == 1
