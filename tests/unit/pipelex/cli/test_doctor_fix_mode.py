"""Unit tests for doctor's interactive fix mode and manual-fix guidance in do_doctor_cmd."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from pipelex.cli.commands.doctor_cmd import BackendFileReport, TelemetryConfigCheck, TelemetryConfigFinding, do_doctor_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.model_backends.backend_library import BackendCredentialsReport
from pipelex.cogt.models.deck_manifest import DeckFileStatus, DeckSyncReport
from pipelex.core.validation import MIGRATE_COMMAND

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

CLEAN_DECK = DeckSyncReport(kit_version="1.2.0", installed_kit_version="1.2.0", manifest_present=True, files={})
HEALTHY_TELEMETRY = TelemetryConfigCheck(finding=TelemetryConfigFinding.HEALTHY, message="OK")


class TestDoctorFixMode:
    @pytest.fixture
    def doctor_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub every check healthy plus the display/bootstrap; tests flip what they need."""
        mocks: dict[str, Any] = {
            "setup": mocker.patch("pipelex.cli.commands.doctor_cmd.setup_doctor_runtime"),
            "config": mocker.patch("pipelex.cli.commands.doctor_cmd.check_config_files", return_value=(True, 0, "OK")),
            "telemetry": mocker.patch("pipelex.cli.commands.doctor_cmd.check_telemetry_config", return_value=HEALTHY_TELEMETRY),
            "backends": mocker.patch("pipelex.cli.commands.doctor_cmd.check_backend_credentials", return_value=(True, {}, "OK")),
            "models": mocker.patch("pipelex.cli.commands.doctor_cmd.check_models", return_value=(True, "OK", {})),
            "deck": mocker.patch("pipelex.cli.commands.doctor_cmd.check_deck_sync", return_value=(True, CLEAN_DECK, "OK")),
            "display": mocker.patch("pipelex.cli.commands.doctor_cmd.display_health_report"),
            "init_cmd": mocker.patch("pipelex.cli.commands.doctor_cmd.init_cmd"),
            "update_cmd": mocker.patch("pipelex.cli.commands.doctor_cmd.update_cmd"),
            "replace": mocker.patch("pipelex.cli.commands.doctor_cmd.replace_backend_file", return_value=True),
            "confirm": mocker.patch("pipelex.cli.commands.doctor_cmd.Confirm.ask", return_value=True),
        }
        recorded_console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.doctor_cmd.get_console", return_value=recorded_console)
        mocks["console"] = recorded_console
        return mocks

    def _run_doctor_expecting_exit_one(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            do_doctor_cmd(fix=True)
        assert exc_info.value.code == 1

    def test_fix_missing_config_files_runs_init_config(self, doctor_mocks: dict[str, Any]) -> None:
        """Accepting the config fix runs init focused on config files."""
        doctor_mocks["config"].return_value = (False, 2, "2 configuration file(s) missing")

        self._run_doctor_expecting_exit_one()

        doctor_mocks["init_cmd"].assert_called_once_with(focus=InitFocus.CONFIG, skip_confirmation=True)
        output = doctor_mocks["console"].export_text()
        assert "Interactive Fix Mode" in output
        assert "Configuration files installed" in output

    def test_fix_missing_telemetry_runs_init_telemetry(self, doctor_mocks: dict[str, Any]) -> None:
        """A telemetry file that is not there is written, and it is the only finding that is."""
        doctor_mocks["telemetry"].return_value = TelemetryConfigCheck(
            finding=TelemetryConfigFinding.NOT_FOUND,
            message="Telemetry configuration file not found",
        )

        self._run_doctor_expecting_exit_one()

        doctor_mocks["init_cmd"].assert_called_once_with(focus=InitFocus.TELEMETRY, skip_confirmation=True)
        assert "Telemetry configured" in doctor_mocks["console"].export_text()

    def test_fix_never_offers_to_reset_an_out_of_date_telemetry_file(self, doctor_mocks: dict[str, Any]) -> None:
        """The defect this milestone retired, pinned as behaviour.

        `--fix` used to read the row's *message* for "format has changed" and, on a match, offer
        to write a fresh telemetry.toml — discarding the PostHog key, the Langfuse credentials
        and the exporters that the migration it should have named would have carried forward.
        """
        doctor_mocks["telemetry"].return_value = TelemetryConfigCheck(
            finding=TelemetryConfigFinding.OUT_OF_DATE,
            message=f"Configuration is out of date — run '{MIGRATE_COMMAND}' to bring it up to date",
        )

        self._run_doctor_expecting_exit_one()

        doctor_mocks["init_cmd"].assert_not_called()

    def test_fix_never_offers_to_reset_an_invalid_telemetry_file(self, doctor_mocks: dict[str, Any]) -> None:
        """A file that is wrong is a person's to edit; a reset is offered as a way to start over.

        The distinction matters on the same file the previous test is about: the old sniff also
        matched "invalid configuration", so a single mistyped enum value was answered by
        rewriting the whole file.
        """
        doctor_mocks["telemetry"].return_value = TelemetryConfigCheck(
            finding=TelemetryConfigFinding.INVALID,
            message="Invalid configuration:\nValidation error(s):",
        )

        self._run_doctor_expecting_exit_one()

        doctor_mocks["init_cmd"].assert_not_called()
        output = doctor_mocks["console"].export_text()
        assert "Telemetry validation error" in output
        assert "discarding what is in it" in output

    def test_fix_outdated_deck_runs_update(self, doctor_mocks: dict[str, Any]) -> None:
        """Accepting the deck fix runs `pipelex update --yes`."""
        dirty_deck = DeckSyncReport(
            kit_version="1.3.0",
            installed_kit_version="1.2.0",
            manifest_present=True,
            files={"deck.toml": DeckFileStatus.CLEAN_BEHIND},
        )
        doctor_mocks["deck"].return_value = (False, dirty_deck, "deck out of date")

        self._run_doctor_expecting_exit_one()

        doctor_mocks["update_cmd"].assert_called_once_with(yes=True)
        assert "Model deck updated" in doctor_mocks["console"].export_text()

    def _make_invalid_backend_report(self, tmp_path: Path) -> BackendFileReport:
        return BackendFileReport(
            backend_name="openai",
            file_path=str(tmp_path / "inference" / "backends" / "openai.toml"),
            is_valid=False,
            error_message="openai: bad spec",
            has_kit_template=True,
        )

    def test_fix_backend_file_replacement_accepted(self, doctor_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Accepting the backend replace copies the kit template into the right config dir."""
        bad_report = self._make_invalid_backend_report(tmp_path)
        doctor_mocks["models"].return_value = (False, "Backend configuration error: openai: bad spec", {"openai": bad_report})

        self._run_doctor_expecting_exit_one()

        doctor_mocks["replace"].assert_called_once_with("openai", dry_run=False, config_dir=tmp_path)
        assert "Replaced openai backend configuration" in doctor_mocks["console"].export_text()

    def test_fix_backend_file_replacement_declined(self, doctor_mocks: dict[str, Any], tmp_path: Path) -> None:
        """Declining the backend replace leaves the file alone and reports the skip."""
        bad_report = self._make_invalid_backend_report(tmp_path)
        doctor_mocks["models"].return_value = (False, "Backend configuration error: openai: bad spec", {"openai": bad_report})
        doctor_mocks["confirm"].return_value = False

        self._run_doctor_expecting_exit_one()

        doctor_mocks["replace"].assert_not_called()
        assert "Skipped openai" in doctor_mocks["console"].export_text()

    def test_fix_backend_replacement_failure_reported(self, doctor_mocks: dict[str, Any], tmp_path: Path) -> None:
        """A failed template copy is reported without aborting the doctor run."""
        bad_report = self._make_invalid_backend_report(tmp_path)
        doctor_mocks["models"].return_value = (False, "Backend configuration error: openai: bad spec", {"openai": bad_report})
        doctor_mocks["replace"].return_value = False

        self._run_doctor_expecting_exit_one()

        assert "Failed to replace openai" in doctor_mocks["console"].export_text()

    def test_manual_fixes_for_config_validation_error(self, doctor_mocks: dict[str, Any]) -> None:
        """A config validation error (nothing missing) lands in the manual-fixes section."""
        doctor_mocks["config"].return_value = (False, 0, "Configuration validation failed: bad field")

        self._run_doctor_expecting_exit_one()

        doctor_mocks["init_cmd"].assert_not_called()
        output = doctor_mocks["console"].export_text()
        assert "Manual Fixes Required" in output
        assert "Configuration validation error:" in output
        assert "pipelex init config" in output

    def test_manual_fixes_for_missing_credentials(self, doctor_mocks: dict[str, Any]) -> None:
        """Missing backend credentials produce env-var setup guidance for every platform."""
        credentials_report = BackendCredentialsReport(
            backend_name="openai",
            required_vars=["OPENAI_API_KEY"],
            missing_vars=["OPENAI_API_KEY"],
            placeholder_vars=[],
            all_credentials_valid=False,
        )
        doctor_mocks["backends"].return_value = (False, {"openai": credentials_report}, "1 backend(s) have missing or invalid credentials")

        self._run_doctor_expecting_exit_one()

        output = doctor_mocks["console"].export_text()
        assert "Manual Fixes Required" in output
        assert "Backend credentials:" in output
        assert "OPENAI_API_KEY=your_value_here" in output
        assert "export OPENAI_API_KEY=your_value_here" in output

    def test_fix_mode_with_all_healthy_exits_zero(self, doctor_mocks: dict[str, Any]) -> None:
        """With everything healthy, fix mode exits 0 without prompting."""
        with pytest.raises(SystemExit) as exc_info:
            do_doctor_cmd(fix=True)

        assert exc_info.value.code == 0
        doctor_mocks["confirm"].assert_not_called()
