"""Unit tests for the CLI error handlers not covered by test_error_handlers.py.

Covers the shared panel renderer, the gateway/telemetry/signature handlers, and the
detailed sections of bundle-validation error display. Assertions are on the recorded
plain-text console output plus the exit code.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.error_handlers import (
    ErrorContext,
    display_error_panel,
    handle_gateway_api_key_missing_error,
    handle_gateway_do_not_track_conflict_error,
    handle_gateway_terms_not_accepted_error,
    handle_gateway_unknown_model_error,
    handle_model_deck_preset_error,
    handle_remote_config_unavailable_error,
    handle_remote_config_validation_error,
    handle_telemetry_config_validation_error,
    handle_validate_bundle_error,
)
from pipelex.cogt.exceptions import GatewayUnknownModelError, ModelDeckPresetValidatonError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTermsNotAcceptedError,
    RemoteConfigUnavailableError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestErrorHandlersExtended:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        """Recorded console patched into the error handlers module."""
        recorded_console = Console(width=120, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=recorded_console)
        return recorded_console

    def test_display_error_panel_full_layout(self) -> None:
        """The panel renders title, aligned fields, error, tip and links in order."""
        console = Console(width=120, record=True, color_system=None)
        display_error_panel(
            console,
            title="Something failed",
            fields=[("Pipe", "'my_pipe'"), ("Model Choice", "'gpt-5'")],
            error_message="model not found",
            tip="try another model",
            links=[("Docs", "https://docs.example.com")],
        )
        output = console.export_text()
        assert "❌ Something failed" in output
        assert "Pipe:         'my_pipe'" in output
        assert "Model Choice: 'gpt-5'" in output
        assert "Error: model not found" in output
        assert "💡 Tip: try another model" in output
        assert "Docs: https://docs.example.com" in output

    def test_display_error_panel_omits_error_block_when_none(self) -> None:
        """A None error_message omits the Error block entirely."""
        console = Console(width=120, record=True, color_system=None)
        display_error_panel(
            console,
            title="Soft failure",
            fields=[],
            error_message=None,
            tip="a tip",
            links=[],
        )
        output = console.export_text()
        assert "Error:" not in output
        assert "💡 Tip: a tip" in output

    def test_display_error_panel_multi_line_tip(self) -> None:
        """Multi-line tips keep their line structure."""
        console = Console(width=120, record=True, color_system=None)
        display_error_panel(
            console,
            title="Failure",
            fields=[],
            error_message=None,
            tip="first line\nsecond line",
            links=[],
        )
        output = console.export_text()
        assert "first line" in output
        assert "second line" in output

    def _make_deck_preset_error(self, enabled_backends: set[str] | None) -> ModelDeckPresetValidatonError:
        return ModelDeckPresetValidatonError(
            message="preset references unavailable model",
            model_type=ModelType.LLM,
            preset_id="default_text",
            model_handle="gpt-5",
            enabled_backends=enabled_backends,
        )

    def test_handle_model_deck_preset_error_builds_solutions_tip(self, console: Console) -> None:
        """Without user-action advice, the handler builds the 'Possible solutions' tip."""
        exc = self._make_deck_preset_error(enabled_backends={"openai", "anthropic"})

        with pytest.raises(typer.Exit) as exc_info:
            handle_model_deck_preset_error(exc, context=ErrorContext.VALIDATION)

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Preset ID:" in output
        assert "'default_text'" in output
        assert "Enabled Backends:" in output
        assert "anthropic, openai" in output
        assert "Possible solutions:" in output
        assert "Configure model 'gpt-5' in one of your enabled backends" in output

    def test_handle_model_deck_preset_error_uses_user_action_detail(self, console: Console) -> None:
        """When the error carries user-action advice, it becomes the tip verbatim."""
        exc = self._make_deck_preset_error(enabled_backends=None)
        exc.user_action = UserAction(kind=UserActionKind.CHANGE_MODEL, detail="switch to gpt-4o in the preset")

        with pytest.raises(typer.Exit):
            handle_model_deck_preset_error(exc, context=ErrorContext.VALIDATION)

        output = console.export_text()
        assert "switch to gpt-4o in the preset" in output
        assert "Possible solutions:" not in output
        assert "Enabled Backends:" not in output

    def test_handle_validate_bundle_error_renders_all_sections(self, console: Console) -> None:
        """Blueprint, pipe, and dry-run sections all render with their details."""
        blueprint_error = PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
            domain_code="demo",
            source="bundle.mthds",
            pipe_code="my_pipe",
            message="input variable 'topic' is missing",
            variable_names=["topic"],
        )
        pipe_error = PipesAndConceptValidationErrorData(
            domain_code="demo",
            pipe_code="other_pipe",
            concept_code="Report",
            field_name="output",
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
            message="output concept mismatch",
            field_path="pipes.other_pipe.output",
            variable_names=["report"],
        )
        exc = ValidateBundleError(
            message="validation failed",
            pipelex_bundle_blueprint_validation_errors=[blueprint_error],
            pipe_validation_errors=[pipe_error],
            dry_run_error_message="dry run exploded",
        )

        with pytest.raises(typer.Exit) as exc_info:
            handle_validate_bundle_error(exc, bundle_path=Path("methods/demo.mthds"))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "❌ Bundle validation failed" in output
        assert "Bundle: methods/demo.mthds" in output
        assert "Blueprint Validation Errors:" in output
        assert "Missing Input Variable" in output
        assert "input variable 'topic' is missing" in output
        assert "└─ Source: bundle.mthds" in output
        assert "Pipe Validation Errors:" in output
        assert "Inadequate Output Concept" in output
        assert "Field: output" in output
        assert "└─ Path: pipes.other_pipe.output" in output
        assert "Dry Run Error:" in output
        assert "dry run exploded" in output

    def test_handle_validate_bundle_error_minimal_skips_sections(self, console: Console) -> None:
        """With no detail lists and no bundle path, only the banner and tip render."""
        exc = ValidateBundleError(message="validation failed")

        with pytest.raises(typer.Exit):
            handle_validate_bundle_error(exc)

        output = console.export_text()
        assert "❌ Bundle validation failed" in output
        assert "Bundle:" not in output
        assert "Blueprint Validation Errors:" not in output
        assert "Pipe Validation Errors:" not in output
        assert "Dry Run Error:" not in output
        assert "💡 Tip:" in output
        # A non-signature bundle error must NOT advertise the signature opt-out: signatures are a
        # runnability fact reported via pending_signatures, not a ValidateBundleError (the old
        # signature-specific tip used to leak here from the deleted handle_signatures_not_allowed_error).
        assert "--allow-signatures" not in output

    def test_handle_telemetry_config_validation_error(self, console: Console) -> None:
        """The telemetry handler explains the format migration."""
        exc = TelemetryConfigValidationError("old flat format")

        with pytest.raises(typer.Exit) as exc_info:
            handle_telemetry_config_validation_error(exc)

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Telemetry configuration format has changed" in output
        assert "pipelex init telemetry" in output

    def test_handle_gateway_terms_not_accepted_error(self, console: Console) -> None:
        """The terms handler points at init config and the BYOK alternative."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_gateway_terms_not_accepted_error(GatewayTermsNotAcceptedError())

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Pipelex Gateway terms not accepted" in output
        assert "pipelex init config" in output
        assert "Disable pipelex_gateway" in output

    def test_handle_gateway_api_key_missing_error(self, console: Console) -> None:
        """The API-key handler names the env var to set."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_gateway_api_key_missing_error(GatewayApiKeyMissingError())

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Pipelex Gateway API key not set" in output
        assert "PIPELEX_GATEWAY_API_KEY" in output

    def test_handle_gateway_do_not_track_conflict_error(self, console: Console) -> None:
        """The DNT handler offers both resolution options."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_gateway_do_not_track_conflict_error(GatewayDoNotTrackConflictError(dnt_env_var="DO_NOT_TRACK"))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Pipelex Gateway requires telemetry" in output
        assert "Unset" in output
        assert "disable pipelex_gateway" in output

    def test_handle_remote_config_validation_error(self, console: Console) -> None:
        """A malformed gateway config is flagged as a server-side bug to report."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_remote_config_validation_error(RemoteConfigValidationError("missing key 'models'"))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Pipelex Gateway configuration is invalid" in output
        assert "missing key 'models'" in output
        assert "Please report this!" in output

    def test_handle_remote_config_unavailable_error(self, console: Console) -> None:
        """Offline with a cold cache yields reconnect-or-BYOK guidance."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_remote_config_unavailable_error(RemoteConfigUnavailableError("no network, no cache"))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "unreachable and no cached config" in output
        assert "no network, no cache" in output
        assert "pipelex init" in output

    @pytest.mark.parametrize(
        ("config_source", "expected_phrase"),
        [
            (RemoteConfigSource.FRESH, "Check the model handle for typos"),
            (RemoteConfigSource.CACHED, "cache may be stale"),
        ],
    )
    def test_handle_gateway_unknown_model_error_branches_on_source(
        self,
        console: Console,
        config_source: RemoteConfigSource,
        expected_phrase: str,
    ) -> None:
        """The unknown-model handler branches its remediation on config provenance."""
        exc = GatewayUnknownModelError(model_name="mystery-model", source=config_source)

        with pytest.raises(typer.Exit) as exc_info:
            handle_gateway_unknown_model_error(exc)

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "Unknown gateway model handle" in output
        assert "'mystery-model'" in output
        assert expected_phrase in output

    def test_handlers_escape_rich_markup_in_messages(self, console: Console) -> None:
        """Square brackets in exception text must render literally, not as markup."""
        exc = RemoteConfigValidationError("payload has [red]markup[/red] inside")

        with pytest.raises(typer.Exit):
            handle_remote_config_validation_error(exc)

        output = console.export_text()
        assert "payload has [red]markup[/red] inside" in output
