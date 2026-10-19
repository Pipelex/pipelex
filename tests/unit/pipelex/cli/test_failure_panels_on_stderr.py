from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import click
import pytest
import typer

from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_former_release_config_error,
    handle_model_availability_error,
    handle_model_choice_error,
    handle_model_deck_preset_error,
    handle_telemetry_config_validation_error,
    handle_validate_bundle_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidationError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _model_choice() -> None:
    exc = PipeOperatorModelChoiceError(
        message="model 'gpt-5' not found",
        pipe_type="llm_text",
        pipe_code="my_pipe",
        domain_code="my_domain",
        field_name="model",
        model_type=ModelType.LLM,
        model_choice="gpt-5",
    )
    try:
        raise exc
    except PipeOperatorModelChoiceError:
        handle_model_choice_error(exc, context=ErrorContext.PIPE_RUN)


def _model_availability() -> None:
    exc = PipeOperatorModelAvailabilityError(
        message="model not available",
        run_mode=PipeRunMode.LIVE,
        pipe_type="llm_text",
        pipe_code="my_pipe",
        pipe_stack=["my_pipe"],
        model_handle="gpt-4o",
        fallback_list=["gpt-4o-mini"],
    )
    try:
        raise exc
    except PipeOperatorModelAvailabilityError:
        handle_model_availability_error(exc, context=ErrorContext.PIPE_RUN)


def _deck_preset() -> None:
    exc = ModelDeckPresetValidationError(
        message="preset references unavailable model",
        model_type=ModelType.LLM,
        preset_id="default",
        model_handle="gpt-5",
        enabled_backends={"openai"},
    )
    try:
        raise exc
    except ModelDeckPresetValidationError:
        handle_model_deck_preset_error(exc, context=ErrorContext.VALIDATION)


def _validate_bundle() -> None:
    exc = ValidateBundleError(message="validation failed")
    try:
        raise exc
    except ValidateBundleError:
        handle_validate_bundle_error(exc)


def _telemetry() -> None:
    exc = TelemetryConfigValidationError("'custom_posthog.mode': invalid enum value")
    try:
        raise exc
    except TelemetryConfigValidationError:
        handle_telemetry_config_validation_error(exc)


def _former_release() -> None:
    exc = FormerReleaseConfigError("This configuration was set up by a former Pipelex release.")
    try:
        raise exc
    except FormerReleaseConfigError:
        handle_former_release_config_error(exc=exc)


class TestFailurePanelsOnStderr:
    @pytest.mark.parametrize(
        ("render", "heading"),
        [
            (_model_choice, "Pipe run failed because of a model choice could not be interpreted correctly"),
            (_model_availability, "Pipe run failed because a model wasn't available"),
            (_deck_preset, "failed due to model deck preset validation error"),
            (_validate_bundle, "Bundle validation failed"),
            (_telemetry, "Telemetry configuration could not be loaded"),
            (_former_release, "Configuration left by a former release"),
        ],
    )
    @pytest.mark.parametrize("traceback_requested", [False, True])
    @pytest.mark.builds_problems_without_required_params(
        reason="builds its failures in the test with a message alone, to check which stream their panels go to"
    )
    def test_a_dedicated_panel_and_its_traceback_go_to_stderr(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        render: Callable[[], None],
        heading: str,
        traceback_requested: bool,
    ) -> None:
        """A failure's panel is the failure's report, so stdout keeps only what the command produced, under --traceback too."""
        mocker.patch("pipelex.cli.error_handlers.is_traceback_requested", return_value=traceback_requested)
        ctx = click.Context(click.Command("test"), obj={"traceback": traceback_requested})

        with ctx, pytest.raises(typer.Exit) as exit_info:
            render()

        assert exit_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert heading in captured.err
        assert ("Traceback" in captured.err) is traceback_requested
