"""Unit tests for the agent CLI factory function."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTermsNotAcceptedError,
    RemoteConfigValidationError,
)
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.misc.pretty import PrettyPrinter


class TestMakePipelexForAgentCli:
    """Tests for make_pipelex_for_agent_cli JSON error output."""

    @pytest.fixture(autouse=True)
    def _restore_globals(self):
        """Restore PrettyPrinter.mode, root log level, and the process-global
        ``logging.disable`` threshold after tests that call the factory successfully —
        otherwise the agent CLI cutoff (armed by ``silence_logging_for_agent_cli`` inside
        the factory) leaks into other tests in the suite.
        """
        original_mode = PrettyPrinter.mode
        root_logger = logging.getLogger()
        original_level: int = root_logger.level
        original_disable = logging.root.manager.disable
        yield
        PrettyPrinter.mode = original_mode
        root_logger.setLevel(original_level)
        logging.disable(original_disable)

    def test_successful_initialization(self, mocker: MockerFixture) -> None:
        """Should return the Pipelex instance when make() succeeds."""
        mock_pipelex = mocker.MagicMock()
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", return_value=mock_pipelex)
        result = make_pipelex_for_agent_cli()
        assert result is mock_pipelex

    @pytest.mark.parametrize(
        ("exc_class", "exc_args", "expected_error_type"),
        [
            (TelemetryConfigValidationError, ("telemetry config bad",), "TelemetryConfigValidationError"),
            (GatewayTermsNotAcceptedError, (), "GatewayTermsNotAcceptedError"),
            (GatewayApiKeyMissingError, (), "GatewayApiKeyMissingError"),
            (GatewayDoNotTrackConflictError, ("DO_NOT_TRACK",), "GatewayDoNotTrackConflictError"),
            (RemoteConfigValidationError, ("bad remote config",), "RemoteConfigValidationError"),
        ],
    )
    def test_initialization_error_produces_json(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        exc_class: type[Exception],
        exc_args: tuple[str, ...],
        expected_error_type: str,
    ) -> None:
        """Each initialization exception should produce JSON stderr with the correct error_type."""
        mocker.patch(
            "pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make",
            side_effect=exc_class(*exc_args),
        )

        with pytest.raises(typer.Exit) as exc_info:
            make_pipelex_for_agent_cli()
        assert exc_info.value.exit_code == 1

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == expected_error_type
        assert "message" in parsed

    def test_model_deck_preset_error_includes_structured_fields(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ModelDeckPresetValidatonError should include preset_id, model_type, model_handle, enabled_backends."""
        exc = ModelDeckPresetValidatonError(
            message="preset validation failed",
            preset_id="my_preset",
            model_type=ModelType.LLM,
            model_handle="claude-3-opus",
            enabled_backends={"openai", "anthropic"},
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make",
            side_effect=exc,
        )

        with pytest.raises(typer.Exit):
            make_pipelex_for_agent_cli()

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_type"] == "ModelDeckPresetValidatonError"
        assert parsed["preset_id"] == "my_preset"
        assert parsed["model_handle"] == "claude-3-opus"
        assert sorted(parsed["enabled_backends"]) == ["anthropic", "openai"]
