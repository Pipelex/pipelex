"""Unit tests for the agent CLI factory function."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.base_exceptions import MigrationErrorBlock, PipelexConfigError, PipelexSetupError
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, start_agent_cli_error_format
from pipelex.cogt.exceptions import ModelDeckPresetValidationError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.telemetry.exceptions import TelemetryApiKeyMissingError, TelemetryConfigValidationError
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
        ("exc_class", "exc_args", "expected_error_class"),
        [
            (TelemetryConfigValidationError, ("telemetry config bad",), "TelemetryConfigValidationError"),
        ],
    )
    def test_initialization_error_produces_json(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        exc_class: type[Exception],
        exc_args: tuple[str, ...],
        expected_error_class: str,
    ) -> None:
        """Each initialization exception is reported as its problem on stderr, its class in the operator's diagnostics."""
        mocker.patch(
            "pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make",
            side_effect=exc_class(*exc_args),
        )

        with pytest.raises(typer.Exit) as exc_info:
            make_pipelex_for_agent_cli()
        assert exc_info.value.exit_code == 1

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == "pipelex.config.invalid"
        assert parsed["domain"] == "operator"
        assert parsed["diagnostics"]["error_class"] == expected_error_class
        assert parsed["message"] == "telemetry config bad"
        assert "hint" not in parsed

    def test_model_deck_preset_error_includes_structured_fields(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ModelDeckPresetValidationError should include preset_id, model_type, model_handle, enabled_backends."""
        exc = ModelDeckPresetValidationError(
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
        assert parsed["diagnostics"]["error_class"] == "ModelDeckPresetValidationError"
        assert parsed["preset_id"] == "my_preset"
        assert parsed["model_handle"] == "claude-3-opus"
        assert sorted(parsed["enabled_backends"]) == ["anthropic", "openai"]

    @pytest.mark.parametrize(
        ("failure", "expected_code"),
        [
            (RuntimeError("the disk is full"), "runtime.unexpected"),
            (PipelexSetupError("Pipelex is already initialized"), "runtime.misconfigured"),
        ],
    )
    def test_a_boot_failure_with_no_advice_tips_the_recovery_path(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], failure: Exception, expected_code: str
    ) -> None:
        """A boot failure whose chain advises nothing is tipped with the recovery path an agent can run, and keeps its code."""
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", side_effect=failure)
        start_agent_cli_error_format(root_error_format=CliOutputFormat.MARKDOWN)

        with pytest.raises(typer.Exit):
            make_pipelex_for_agent_cli()

        markdown = capsys.readouterr().err
        assert f"- Code: `{expected_code}`" in markdown
        assert "💡 Run 'pipelex-agent doctor' to diagnose the installation and its configuration." in markdown
        assert "'pipelex-agent migrate --dry-run --format json', shown to the user, then 'pipelex-agent migrate --yes'" in markdown
        assert "'pipelex-agent init' (--global for the home configuration)" in markdown

    @pytest.mark.parametrize(
        ("failure", "expected_code", "expected_message"),
        [
            (RuntimeError("the disk is full"), "runtime.unexpected", "Pipelex initialization failed: the disk is full"),
            (PipelexSetupError("Pipelex is already initialized"), "runtime.misconfigured", "Pipelex is already initialized"),
        ],
    )
    def test_a_boot_failure_keeps_its_code_and_class(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], failure: Exception, expected_code: str, expected_message: str
    ) -> None:
        """Under the boot's tip the problem is the failure's own: its code, and its class as the diagnostics' error class."""
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", side_effect=failure)

        with pytest.raises(typer.Exit):
            make_pipelex_for_agent_cli()

        stderr = capsys.readouterr().err
        parsed = json.loads(stderr)
        assert parsed["code"] == expected_code
        assert parsed["message"] == expected_message
        assert parsed["diagnostics"]["error_class"] == type(failure).__name__
        assert "AgentBootError" not in stderr

        start_agent_cli_error_format(root_error_format=CliOutputFormat.MARKDOWN)
        with pytest.raises(typer.Exit):
            make_pipelex_for_agent_cli()

        assert f"- Error class: `{type(failure).__name__}`" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("migration", "expected_tip"),
        [
            (None, "💡 Run 'pipelex doctor' (from an agent, 'pipelex-agent doctor') to find what in the configuration does not validate"),
            (
                MigrationErrorBlock(remedy=MIGRATE_COMMAND, would_write=True, needs_attention=False, plans=[]),
                "then run 'pipelex-agent migrate --yes'",
            ),
            (
                MigrationErrorBlock(remedy=MIGRATE_COMMAND, would_write=False, needs_attention=True, plans=[]),
                "💡 A migration would rewrite nothing here: correct by hand what the migration's plans name",
            ),
        ],
    )
    def test_a_configuration_that_does_not_load_tips_its_own_advice(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], migration: MigrationErrorBlock | None, expected_tip: str
    ) -> None:
        """A configuration error advises by its migration: doctor, migrate, or correct by hand; its step names the setting."""
        refusal = PipelexConfigError(
            "Could not setup config because of: bad", migration=migration, surface="pipelex", file="pipelex.toml", setting="runtime.log.level"
        )
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", side_effect=refusal)
        start_agent_cli_error_format(root_error_format=CliOutputFormat.MARKDOWN)

        with pytest.raises(typer.Exit):
            make_pipelex_for_agent_cli()

        markdown = capsys.readouterr().err
        assert expected_tip in markdown
        assert "Run 'pipelex-agent doctor' to diagnose the installation" not in markdown
        assert (
            "Correct the setting 'runtime.log.level' in the file 'pipelex.toml' of the pipelex configuration, then restart the runtime." in markdown
        )

    @pytest.mark.parametrize(
        ("refusal", "expected_tip"),
        [
            (
                PipelexConfigError("Error loading configuration: no such file", surface="pipelex", file="pipelex.toml").with_error_code(
                    PipelexErrorCode.CONFIG_FILE_MISSING
                ),
                "💡 A configuration file is missing: restore it, or run 'pipelex init' (from an agent, 'pipelex-agent init', with --global",
            ),
            (
                TelemetryApiKeyMissingError("Custom PostHog is enabled in the telemetry configuration, but its API key is not set"),
                "💡 A variable the configuration reads is not set: set the one the message names",
            ),
            (
                PipelexConfigError("Error loading configuration: bad TOML", surface="pipelex", file="pipelex.toml")
                .with_error_code(PipelexErrorCode.CONFIG_SYNTAX)
                .with_params(line=1, column=9),
                "💡 Run 'pipelex doctor' (from an agent, 'pipelex-agent doctor') to find what in the configuration does not validate",
            ),
        ],
    )
    def test_a_configuration_refusal_s_tip_follows_its_code(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], refusal: PipelexConfigError, expected_tip: str
    ) -> None:
        """A missing file is written by init, a missing variable is set, and only a file that does not validate or parse sends to doctor."""
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", side_effect=refusal)
        start_agent_cli_error_format(root_error_format=CliOutputFormat.MARKDOWN)

        with pytest.raises(typer.Exit):
            make_pipelex_for_agent_cli()

        markdown = capsys.readouterr().err
        assert expected_tip in markdown
        assert markdown.count("💡") == 1
