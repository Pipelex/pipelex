"""Unit tests for execute_run — the sync wrapper around _execute_run.

Covers setup/teardown wiring and the error-handler dispatch at the CLI boundary.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
import typer
from rich.console import Console

from pipelex.base_exceptions import PipelexError, PipelexSetupError
from pipelex.cli.commands.run._run_core import execute_run
from pipelex.cli.error_handlers import ErrorContext
from pipelex.cogt.model_backends.backend_credentials import BackendCredentialsErrorMsgFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _call_execute_run(**overrides: Any) -> None:
    kwargs: dict[str, Any] = {
        "pipe_code": "test_pipe",
        "bundle_path": None,
        "inputs": None,
        "save_working_memory": False,
        "working_memory_path": None,
        "save_main_stuff": False,
        "no_pretty_print": True,
        "graph": None,
        "graph_full_data": None,
        "output_dir": "temp/test_outputs",
        "dry_run": False,
        "mock_usage": False,
        "mock_inputs": False,
        "library_dir": None,
    }
    kwargs.update(overrides)
    execute_run(**kwargs)


class TestExecuteRunWrapper:
    @pytest.fixture
    def wrapper_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub the Pipelex bootstrap, telemetry context, teardown and the async core."""
        telemetry_manager = mocker.MagicMock()
        mocks: dict[str, Any] = {
            "make_pipelex": mocker.patch("pipelex.cli.commands.run._run_core.make_pipelex_for_cli"),
            "telemetry": mocker.patch("pipelex.cli.commands.run._run_core.get_telemetry_manager", return_value=telemetry_manager),
            "tag": mocker.patch("pipelex.cli.commands.run._run_core.tag"),
            "teardown": mocker.patch("pipelex.cli.commands.run._run_core.Pipelex.teardown_if_needed"),
            "core": mocker.patch("pipelex.cli.commands.run._run_core._execute_run", new=mocker.AsyncMock(return_value=None)),
        }
        recorded_console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=recorded_console)
        mocks["console"] = recorded_console
        return mocks

    def test_happy_path_setup_and_teardown(self, wrapper_mocks: dict[str, Any]) -> None:
        """The wrapper boots Pipelex for the CLI, runs the core, and always tears down."""
        _call_execute_run(library_dir=["./libs"])

        make_kwargs = wrapper_mocks["make_pipelex"].call_args.kwargs
        assert make_kwargs["context"] == ErrorContext.VALIDATION_BEFORE_PIPE_RUN
        assert make_kwargs["library_dirs"] == ["./libs"]
        wrapper_mocks["core"].assert_awaited_once()
        wrapper_mocks["teardown"].assert_called_once()

    def test_live_run_boots_keyed(self, wrapper_mocks: dict[str, Any]) -> None:
        """A live run needs credentials: the boot asks for inference."""
        _call_execute_run(dry_run=False)

        make_kwargs = wrapper_mocks["make_pipelex"].call_args.kwargs
        assert make_kwargs["needs_inference"] is True

    def test_dry_run_boots_keyless_with_real_model_specs(self, wrapper_mocks: dict[str, Any]) -> None:
        """`--dry-run` makes no inference call, so it must not demand credentials — the same boot
        `pipelex-agent run --dry-run` uses: keyless, every run forced to DRY.
        """
        _call_execute_run(dry_run=True)

        make_kwargs = wrapper_mocks["make_pipelex"].call_args.kwargs
        assert make_kwargs["needs_inference"] is False

    def test_model_choice_error_dispatched_to_handler(self, wrapper_mocks: dict[str, Any], mocker: MockerFixture) -> None:
        """A model-choice error is routed to its dedicated handler."""
        choice_error = PipeOperatorModelChoiceError(
            message="model 'gpt-5' not found",
            pipe_type="llm_text",
            pipe_code="test_pipe",
            domain_code="my_domain",
            field_name="model",
            model_type=ModelType.LLM,
            model_choice="gpt-5",
        )
        wrapper_mocks["core"].side_effect = choice_error
        handler_mock = mocker.patch("pipelex.cli.commands.run._run_core.handle_model_choice_error")

        _call_execute_run()

        handler_mock.assert_called_once_with(choice_error, context=ErrorContext.PIPE_RUN)
        wrapper_mocks["teardown"].assert_called_once()

    def test_model_availability_error_dispatched_to_handler(self, wrapper_mocks: dict[str, Any], mocker: MockerFixture) -> None:
        """A model-availability error is routed to its dedicated handler."""
        availability_error = PipeOperatorModelAvailabilityError(
            message="model not available",
            run_mode=PipeRunMode.LIVE,
            pipe_type="llm_text",
            pipe_code="test_pipe",
            pipe_stack=["test_pipe"],
            model_handle="gpt-4o",
            fallback_list=[],
        )
        wrapper_mocks["core"].side_effect = availability_error
        handler_mock = mocker.patch("pipelex.cli.commands.run._run_core.handle_model_availability_error")

        _call_execute_run()

        handler_mock.assert_called_once_with(availability_error, context=ErrorContext.PIPE_RUN)

    def test_typer_exit_passes_through(self, wrapper_mocks: dict[str, Any]) -> None:
        """A typer.Exit from the core propagates untouched (already user-reported)."""
        wrapper_mocks["core"].side_effect = typer.Exit(1)

        with pytest.raises(typer.Exit) as exc_info:
            _call_execute_run()

        assert exc_info.value.exit_code == 1
        wrapper_mocks["teardown"].assert_called_once()

    @pytest.mark.parametrize(
        "message",
        [
            "the pipe blew up",
            "Model 'gpt-5 → SDK[openai]•Backend[openai]•Model[gpt-5-2025]' does not support documents",
            "Expected list[int], got [red]str[/red]",
        ],
    )
    def test_pipelex_error_prints_message_and_exits(self, wrapper_mocks: dict[str, Any], message: str) -> None:
        """A PipelexError prints the friendly failure message, its own message exactly as written, and exits 1."""
        wrapper_mocks["core"].side_effect = PipelexError(message)

        with pytest.raises(typer.Exit) as exc_info:
            _call_execute_run()

        assert exc_info.value.exit_code == 1
        output = wrapper_mocks["console"].export_text()
        assert "Failed to execute pipeline" in output
        assert message in output

    def test_a_missing_credential_message_prints_the_backend_table_as_written(self, wrapper_mocks: dict[str, Any]) -> None:
        r"""The message names the table as `[openai]`; it used to carry a Rich escape, which the escape here printed as `\[openai]`."""
        message = BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg(
            secrets_provider=EnvSecretsProvider(),
            backend_name="openai",
            var_name="OPENAI_API_KEY",
            suggest_hosted_runs=True,
        )
        wrapper_mocks["core"].side_effect = PipelexSetupError(message)

        with pytest.raises(typer.Exit) as exc_info:
            _call_execute_run()

        assert exc_info.value.exit_code == 1
        output = wrapper_mocks["console"].export_text()
        assert "Add 'enabled = false' under '[openai]' in '.pipelex/inference/backends.toml'" in output
        assert "\\[" not in output

    def test_unexpected_error_logs_its_traceback_and_exits(self, wrapper_mocks: dict[str, Any], mocker: MockerFixture) -> None:
        """An unexpected exception is logged at ERROR with its traceback, which the console does not print a second time, and exits 1.

        The traceback used to be printed on the console alone, so under the `json` or `otlp` sink an unexpected
        failure's stack never reached the log store.
        """
        log_mock = mocker.patch("pipelex.cli.commands.run._run_core.log")
        wrapper_mocks["core"].side_effect = RuntimeError("totally unexpected")

        with pytest.raises(typer.Exit) as exc_info:
            _call_execute_run()

        assert exc_info.value.exit_code == 1
        output = wrapper_mocks["console"].export_text()
        assert "Failed to execute pipeline" in output
        assert "totally unexpected" not in output
        assert "Traceback" not in output
        log_mock.error.assert_called_once_with("The pipeline could not be executed", include_exception=True)

    def test_unexpected_error_reaches_a_structured_sink_with_its_traceback(
        self, wrapper_mocks: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        """The record carries the exception itself, so a structured sink writes the stack the console used to keep to itself."""
        wrapper_mocks["core"].side_effect = RuntimeError("totally unexpected")

        with caplog.at_level(logging.ERROR, logger="pipelex.cli.commands.run._run_core"), pytest.raises(typer.Exit):
            _call_execute_run()

        (record,) = [record for record in caplog.records if record.getMessage() == "The pipeline could not be executed"]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert isinstance(record.exc_info[1], RuntimeError)
        assert str(record.exc_info[1]) == "totally unexpected"
