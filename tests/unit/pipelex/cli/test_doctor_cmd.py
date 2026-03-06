"""Unit tests for the doctor command — layered config resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

from pipelex.cli.commands.doctor_cmd import (
    check_backend_credentials,
    check_telemetry_config,
    do_doctor_cmd,
)
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME

# Minimal valid telemetry TOML — only [custom_posthog].mode is needed, rest defaults
TELEMETRY_OFF = '[custom_posthog]\nmode = "off"\n'
TELEMETRY_ANONYMOUS = '[custom_posthog]\nmode = "anonymous"\n'


class TestDoctorLayeredResolution:
    """Verify that doctor checks use layered config resolution:
    project .pipelex/ first, fall back to global ~/.pipelex/.

    This covers the scenario where pipelex is installed globally and run
    from a project that may or may not have its own .pipelex/ directory.
    """

    def test_do_doctor_cmd_delegates_layered_resolution_to_checks(self, mocker: MockerFixture) -> None:
        """do_doctor_cmd should call check functions with no config_dir so they use layered resolution."""
        mock_check_config = mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_config_files",
            return_value=(True, 0, "OK"),
        )
        mock_check_telemetry = mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_telemetry_config",
            return_value=(True, "OK"),
        )
        mock_check_backends = mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_backend_credentials",
            return_value=(True, {}, "OK"),
        )
        mock_check_models = mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_models",
            return_value=(True, "OK", {}),
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.display_health_report")

        with pytest.raises(SystemExit) as exc_info:
            do_doctor_cmd(fix=False)
        assert exc_info.value.code == 0

        # All checks must be called without config_dir (layered resolution)
        mock_check_config.assert_called_once_with()
        mock_check_telemetry.assert_called_once_with()
        mock_check_backends.assert_called_once_with()
        mock_check_models.assert_called_once_with()

    def test_telemetry_check_falls_back_to_global(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """When project .pipelex/ exists but has no telemetry.toml, fall back to global ~/.pipelex/."""
        global_dir = tmp_path / "global_pipelex"
        project_dir = tmp_path / "project_pipelex"
        # Create both dirs but only put telemetry.toml in global
        global_dir.mkdir()
        project_dir.mkdir()
        (global_dir / TELEMETRY_CONFIG_FILE_NAME).write_text(TELEMETRY_OFF, encoding="utf-8")

        mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)
        mocker.patch.object(ConfigLoader, "global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)

        # No config_dir override → layered resolution should find it in global
        healthy, message = check_telemetry_config()
        assert healthy is True
        assert "off" in message

    def test_telemetry_check_uses_project_override(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """When project .pipelex/ has telemetry.toml, it should be used instead of global."""
        global_dir = tmp_path / "global_pipelex"
        project_dir = tmp_path / "project_pipelex"
        global_dir.mkdir()
        project_dir.mkdir()
        (global_dir / TELEMETRY_CONFIG_FILE_NAME).write_text(TELEMETRY_OFF, encoding="utf-8")
        (project_dir / TELEMETRY_CONFIG_FILE_NAME).write_text(TELEMETRY_ANONYMOUS, encoding="utf-8")

        mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)
        mocker.patch.object(ConfigLoader, "global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)

        healthy, message = check_telemetry_config()
        assert healthy is True
        assert "anonymous" in message

    def test_telemetry_check_with_explicit_config_dir_skips_layering(self, tmp_path: Path) -> None:
        """When config_dir is explicitly provided (e.g. --global), use it directly without layering."""
        explicit_dir = tmp_path / "explicit_pipelex"
        explicit_dir.mkdir()
        (explicit_dir / TELEMETRY_CONFIG_FILE_NAME).write_text(TELEMETRY_OFF, encoding="utf-8")

        healthy, _message = check_telemetry_config(config_dir=explicit_dir)
        assert healthy is True

    def test_backend_credentials_falls_back_to_global(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """When project .pipelex/ exists but has no backends.toml, fall back to global."""
        global_dir = tmp_path / "global_pipelex"
        project_dir = tmp_path / "project_pipelex"
        project_dir.mkdir()
        global_inference_dir = global_dir / "inference"
        global_inference_dir.mkdir(parents=True)

        # Only global has backends.toml — with only the internal backend
        backends_content = "[internal]\nenabled = true\n"
        (global_inference_dir / "backends.toml").write_text(backends_content, encoding="utf-8")

        mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)
        mocker.patch.object(ConfigLoader, "global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)

        _healthy, _, message = check_backend_credentials()
        # Should find backends.toml in global, not report "not found"
        assert "not found" not in message.lower()
