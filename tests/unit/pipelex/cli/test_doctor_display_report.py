"""Unit tests for doctor's display_health_report rendering and the doctor_cmd error guard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from pipelex.cli.commands.doctor_cmd import (
    BackendFileReport,
    ConfigLocationInfo,
    display_health_report,
    doctor_cmd,
)
from pipelex.cogt.model_backends.backend_library import BackendCredentialsReport
from pipelex.cogt.models.deck_manifest import DeckFileStatus, DeckSyncReport

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

CLEAN_DECK = DeckSyncReport(kit_version="1.2.0", installed_kit_version="1.2.0", manifest_present=True, files={})

PROJECT_LOCATION = ConfigLocationInfo(
    config_dir="/work/project/.pipelex",
    is_project_local=True,
    project_root="/work/project",
    global_config_dir="/home/user/.pipelex",
)

GLOBAL_LOCATION = ConfigLocationInfo(
    config_dir="/home/user/.pipelex",
    is_project_local=False,
    project_root=None,
    global_config_dir="/home/user/.pipelex",
)


def _healthy_report_kwargs() -> dict[str, Any]:
    return {
        "config_healthy": True,
        "config_message": "All configuration files present and valid",
        "config_missing_count": 0,
        "telemetry_healthy": True,
        "telemetry_message": "Telemetry configured (mode: off)",
        "backends_healthy": True,
        "backends_message": "All 1 enabled backend(s) have valid credentials",
        "backend_credential_reports": {},
        "models_healthy": True,
        "models_message": "Models are valid",
        "backend_file_reports": {},
        "deck_healthy": True,
        "deck_message": "Deck is up to date with pipelex 1.2.0",
        "deck_report": CLEAN_DECK,
        "config_location": PROJECT_LOCATION,
    }


class TestDoctorDisplayReport:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        recorded_console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.doctor_cmd.get_console", return_value=recorded_console)
        return recorded_console

    def test_all_healthy_report(self, console: Console) -> None:
        """A fully healthy system renders the green banner and project-local location."""
        display_health_report(**_healthy_report_kwargs())

        output = console.export_text()
        assert "Overall Status: ✅ All systems healthy" in output
        assert "Using project config: /work/project/.pipelex" in output
        assert "Project root: /work/project" in output
        assert "Configuration Files" in output
        assert "Telemetry Configuration" in output
        assert "Backend Credentials" in output
        assert "Models are valid" in output
        assert "Deck is up to date with pipelex 1.2.0" in output
        assert "Possible Solutions" not in output

    def test_global_location_rendered(self, console: Console) -> None:
        """Without a project .pipelex/, the global location line is rendered."""
        kwargs = _healthy_report_kwargs()
        kwargs["config_location"] = GLOBAL_LOCATION

        display_health_report(**kwargs)

        output = console.export_text()
        assert "Using global config: /home/user/.pipelex" in output
        assert "No project .pipelex/ directory found" in output

    def test_unhealthy_config_suggests_init(self, console: Console) -> None:
        """Missing config files render the failure row and the init-config solution."""
        kwargs = _healthy_report_kwargs()
        kwargs["config_healthy"] = False
        kwargs["config_message"] = "2 configuration file(s) missing"
        kwargs["config_missing_count"] = 2

        display_health_report(**kwargs)

        output = console.export_text()
        assert "Overall Status: ⚠️  Issues Found" in output
        assert "✗ 2 configuration file(s) missing" in output
        assert "Possible Solutions" in output
        assert "pipelex init config" in output
        assert "pipelex doctor --fix" in output

    def test_credential_details_rendered_per_backend(self, console: Console) -> None:
        """Backend credential issues list missing and placeholder vars per backend."""
        kwargs = _healthy_report_kwargs()
        kwargs["backends_healthy"] = False
        kwargs["backends_message"] = "2 backend(s) have missing or invalid credentials"
        kwargs["backend_credential_reports"] = {
            "openai": BackendCredentialsReport(
                backend_name="openai",
                required_vars=["OPENAI_API_KEY"],
                missing_vars=["OPENAI_API_KEY"],
                placeholder_vars=[],
                all_credentials_valid=False,
            ),
            "mistral": BackendCredentialsReport(
                backend_name="mistral",
                required_vars=["MISTRAL_API_KEY"],
                missing_vars=[],
                placeholder_vars=["MISTRAL_API_KEY"],
                all_credentials_valid=False,
            ),
            "anthropic": BackendCredentialsReport(
                backend_name="anthropic",
                required_vars=["ANTHROPIC_API_KEY"],
                missing_vars=[],
                placeholder_vars=[],
                all_credentials_valid=True,
            ),
        }

        display_health_report(**kwargs)

        output = console.export_text()
        assert "Missing: OPENAI_API_KEY" in output
        assert "Placeholders: MISTRAL_API_KEY" in output
        assert "All credentials set" in output
        assert "Set the following environment variables:" in output
        assert "Replace placeholder values for:" in output

    def test_models_skipped_advisory(self, console: Console) -> None:
        """A skipped models check renders as an advisory, not a failure."""
        kwargs = _healthy_report_kwargs()
        kwargs["models_healthy"] = False
        kwargs["models_message"] = "skipped — fix configuration errors first"
        kwargs["models_skipped"] = True

        display_health_report(**kwargs)

        output = console.export_text()
        assert "Models check deferred until config errors are fixed." in output

    def test_backend_file_issue_details(self, console: Console) -> None:
        """Invalid backend files show kit-template vs custom-backend guidance."""
        kwargs = _healthy_report_kwargs()
        kwargs["models_healthy"] = False
        kwargs["models_message"] = "Backend configuration error: openai: bad spec"
        kwargs["backend_file_reports"] = {
            "openai": BackendFileReport(
                backend_name="openai",
                file_path="/cfg/inference/backends/openai.toml",
                is_valid=False,
                error_message="openai: bad spec\nmore detail",
                has_kit_template=True,
            ),
            "custom_llm": BackendFileReport(
                backend_name="custom_llm",
                file_path="/cfg/inference/backends/custom_llm.toml",
                is_valid=False,
                error_message="custom_llm: unknown field",
                has_kit_template=False,
            ),
        }

        display_health_report(**kwargs)

        output = console.export_text()
        assert "Backend configuration format may be outdated" in output
        assert "Template available for replacement" in output
        assert "This appears to be a custom backend - manual fix required" in output
        assert "openai: bad spec" in output
        assert "more detail" not in output
        assert "pipelex doctor --fix" in output
        assert "Manually fix backend configuration in" in output
        assert "custom_llm.toml" in output

    def test_deck_drift_per_file_detail(self, console: Console) -> None:
        """Deck drift lists each actionable file with its status label."""
        kwargs = _healthy_report_kwargs()
        kwargs["deck_healthy"] = False
        kwargs["deck_message"] = "1 deck file(s) need action"
        kwargs["deck_report"] = DeckSyncReport(
            kit_version="1.2.0",
            installed_kit_version="1.2.0",
            manifest_present=True,
            files={"deck.toml": DeckFileStatus.LOCALLY_MODIFIED, "ok.toml": DeckFileStatus.UP_TO_DATE},
        )

        display_health_report(**kwargs)

        output = console.export_text()
        assert "1 deck file(s) need action" in output
        assert "deck.toml" in output
        assert "pipelex update" in output

    def test_fix_mode_announces_interactive_fixes(self, console: Console) -> None:
        """In fix mode, auto-fixable backend issues announce the upcoming prompts."""
        kwargs = _healthy_report_kwargs()
        kwargs["models_healthy"] = False
        kwargs["models_message"] = "Backend configuration error"
        kwargs["backend_file_reports"] = {
            "openai": BackendFileReport(
                backend_name="openai",
                file_path="/cfg/inference/backends/openai.toml",
                is_valid=False,
                has_kit_template=True,
            ),
        }
        kwargs["fix_mode"] = True

        display_health_report(**kwargs)

        output = console.export_text()
        assert "Interactive fixes for outdated backend configurations will be offered below" in output
        assert "Run pipelex doctor --fix" not in output

    def test_doctor_cmd_catches_unexpected_errors(self, console: Console, mocker: MockerFixture) -> None:
        """The doctor entry point converts unexpected errors into a friendly exit 1."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.do_doctor_cmd", side_effect=RuntimeError("totally unexpected"))

        with pytest.raises(SystemExit) as exc_info:
            doctor_cmd()

        assert exc_info.value.code == 1
        output = console.export_text()
        assert "✗ Unexpected error: totally unexpected" in output
        assert "https://go.pipelex.com/discord" in output
