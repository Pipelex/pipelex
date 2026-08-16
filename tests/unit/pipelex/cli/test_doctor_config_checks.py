"""Unit tests for doctor's config-location, config-files and telemetry checks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.cli.commands.doctor_cmd import (
    TelemetryConfigFinding,
    check_config_files,
    check_telemetry_config,
    gather_config_location,
)
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.system.configuration.config_loader import ConfigLoader, config_manager
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.exceptions import ConfigValidationError
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME
from pipelex.tools.misc.exceptions import TomlError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _TinyModel(BaseModel):
    value: int


def _make_validation_error() -> ValidationError:
    try:
        _TinyModel.model_validate({"value": "not-an-int"})
    except ValidationError as exc:
        return exc
    msg = "expected validation to fail"
    raise AssertionError(msg)


class TestDoctorConfigChecks:
    def test_gather_config_location_project_local(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """With a project .pipelex/ resolved, the location is reported as project-local."""
        project_dir = tmp_path / "project" / ".pipelex"
        global_dir = tmp_path / "global"
        mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)
        mocker.patch.object(ConfigLoader, "project_root", new_callable=mocker.PropertyMock, return_value=tmp_path / "project")
        mocker.patch.object(ConfigLoader, "global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)
        mocker.patch.object(ConfigLoader, "pipelex_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)

        location = gather_config_location()

        assert location.is_project_local is True
        assert location.config_dir == str(project_dir)
        assert location.project_root == str(tmp_path / "project")
        assert location.global_config_dir == str(global_dir)

    def test_gather_config_location_global(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Without a project .pipelex/, the location is the global config dir."""
        global_dir = tmp_path / "global"
        mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, return_value=None)
        mocker.patch.object(ConfigLoader, "project_root", new_callable=mocker.PropertyMock, return_value=None)
        mocker.patch.object(ConfigLoader, "global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)
        mocker.patch.object(ConfigLoader, "pipelex_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)

        location = gather_config_location()

        assert location.is_project_local is False
        assert location.project_root is None
        assert location.config_dir == str(global_dir)

    def test_check_config_files_all_good(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """No missing files and no pipelex.toml to validate is healthy."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)

        healthy, missing_count, message = check_config_files(config_dir=tmp_path)

        assert healthy is True
        assert missing_count == 0
        assert message == "All configuration files present and valid"

    def test_check_config_files_missing_files_counted(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Missing config files are counted in the unhealthy message."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=3)

        healthy, missing_count, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert missing_count == 3
        assert message == "3 configuration file(s) missing"

    def test_check_config_files_init_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A failure while probing for missing files is reported as a finding."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", side_effect=PipelexCLIError("probe failed"))

        healthy, missing_count, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert missing_count == 0
        assert "Error checking config files: probe failed" in message

    def test_check_config_files_validation_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A pydantic ValidationError on the merged config produces the migration-aware report."""
        (tmp_path / "pipelex.toml").write_text("[pipelex]\n", encoding="utf-8")
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)
        mocker.patch.object(config_manager, "load_config", return_value={})
        mocker.patch.object(PipelexConfig, "model_validate", side_effect=_make_validation_error())

        healthy, missing_count, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert missing_count == 0
        assert message.startswith("Configuration validation failed:")

    def test_check_config_files_scans_only_the_directory_it_read(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The telemetry row's rule, on the configuration row: `--global` reads one directory.

        A project `pipelex.toml` carrying a key this build knows nothing about, beside the global
        directory under inspection whose own file refuses to load — the report must not name the
        project file, which a `--global` reader never loaded.
        """
        fake_home = tmp_path / "home"
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir(parents=True)
        (global_dir / "pipelex.toml").write_text("[pipelex]\n", encoding="utf-8")
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        (project_root / ".pipelex").mkdir()
        (project_root / ".pipelex" / "pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)
        mocker.patch.object(PipelexConfig, "model_validate", side_effect=_make_validation_error())

        healthy, _, message = check_config_files(config_dir=global_dir)

        assert healthy is False
        assert "not_a_real_setting" not in message
        assert MIGRATE_COMMAND not in message

    def test_check_config_files_config_validation_error_with_cause(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A ConfigValidationError wrapping a ValidationError recovers the original report."""
        (tmp_path / "pipelex.toml").write_text("[pipelex]\n", encoding="utf-8")
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)
        wrapped_error = ConfigValidationError("wrapped")
        wrapped_error.__cause__ = _make_validation_error()
        mocker.patch.object(config_manager, "load_config", side_effect=wrapped_error)

        healthy, _, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert message.startswith("Configuration validation failed:")
        assert "wrapped" not in message

    def test_check_config_files_config_validation_error_without_cause(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A ConfigValidationError without an underlying ValidationError uses its own message."""
        (tmp_path / "pipelex.toml").write_text("[pipelex]\n", encoding="utf-8")
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)
        mocker.patch.object(config_manager, "load_config", side_effect=ConfigValidationError("plain failure"))

        healthy, _, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert message == "Configuration validation failed: plain failure"

    def test_check_config_files_toml_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A TOML parse failure on pipelex.toml is reported as a load error."""
        (tmp_path / "pipelex.toml").write_text("not valid toml [", encoding="utf-8")
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)
        mocker.patch.object(
            config_manager,
            "load_config",
            side_effect=TomlError(message="unterminated table", doc="", pos=0, lineno=1, colno=1),
        )

        healthy, _, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert "Error loading pipelex.toml:" in message
        assert "unterminated table" in message

    def test_check_config_files_os_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """An OSError while loading the config is reported as a load error."""
        (tmp_path / "pipelex.toml").write_text("[pipelex]\n", encoding="utf-8")
        mocker.patch("pipelex.cli.commands.doctor_cmd.init_config", return_value=0)
        mocker.patch.object(config_manager, "load_config", side_effect=OSError("permission denied"))

        healthy, _, message = check_config_files(config_dir=tmp_path)

        assert healthy is False
        assert "Error loading pipelex.toml: permission denied" in message

    def test_check_telemetry_config_file_not_found(self, tmp_path: Path) -> None:
        """A missing telemetry.toml is unhealthy, and is the one finding a fresh file repairs."""
        check = check_telemetry_config(config_dir=tmp_path)

        assert check.finding is TelemetryConfigFinding.NOT_FOUND
        assert check.finding.is_repaired_by_initializing is True
        assert check.message == "Telemetry configuration file not found"

    def test_check_telemetry_config_toml_syntax_error(self, tmp_path: Path) -> None:
        """Invalid TOML in telemetry.toml is reported as a syntax error a person resolves."""
        (tmp_path / TELEMETRY_CONFIG_FILE_NAME).write_text("not [ valid toml", encoding="utf-8")

        check = check_telemetry_config(config_dir=tmp_path)

        assert check.finding is TelemetryConfigFinding.UNPARSEABLE
        assert check.finding.is_repaired_by_initializing is False
        assert check.message.startswith("TOML syntax error:")

    def test_check_telemetry_config_old_format_is_out_of_date_not_broken(self, tmp_path: Path) -> None:
        """The legacy flat format is what the shipped ledger entry is about, so it is migratable.

        This used to be answered with `pipelex init telemetry`, which writes a fresh file over
        the very settings — the PostHog key here — that the migration carries forward.
        """
        (tmp_path / TELEMETRY_CONFIG_FILE_NAME).write_text('telemetry_mode = "off"\nproject_api_key = "key"\n', encoding="utf-8")

        check = check_telemetry_config(config_dir=tmp_path)

        assert check.finding is TelemetryConfigFinding.OUT_OF_DATE
        assert check.finding.is_repaired_by_initializing is False
        assert MIGRATE_COMMAND in check.message
        assert "init telemetry" not in check.message

    def test_check_telemetry_config_invalid_new_format_names_the_field(self, tmp_path: Path) -> None:
        """A current-shape file that fails validation is wrong rather than old, and says which field."""
        (tmp_path / TELEMETRY_CONFIG_FILE_NAME).write_text('[custom_posthog]\nmode = "no-such-mode"\n', encoding="utf-8")

        check = check_telemetry_config(config_dir=tmp_path)

        assert check.finding is TelemetryConfigFinding.INVALID
        assert "custom_posthog.mode" in check.message
        assert MIGRATE_COMMAND not in check.message

    def test_check_telemetry_config_strips_the_reserved_meta_table(self, tmp_path: Path) -> None:
        """`[meta]` belongs to the migration machinery and boot strips it before validating.

        A probe stricter than the loader it reports on would call a perfectly bootable file
        invalid, which is worse than saying nothing.
        """
        (tmp_path / TELEMETRY_CONFIG_FILE_NAME).write_text('[meta]\nschema_version = 2\n\n[custom_posthog]\nmode = "off"\n', encoding="utf-8")

        check = check_telemetry_config(config_dir=tmp_path)

        assert check.finding is TelemetryConfigFinding.HEALTHY

    def test_check_telemetry_config_survives_a_failure_inside_the_scan(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A packaging problem of ours must not replace every row the user came for.

        An exception escaping this probe reaches the doctor's outer handler, which prints one
        line and exits — so the whole health report would be lost to a broken ledger. The
        fallback under-reports at worst, and still names the fields the model refused.
        """
        (tmp_path / TELEMETRY_CONFIG_FILE_NAME).write_text('[custom_posthog]\nmode = "no-such-mode"\n', encoding="utf-8")
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.scan_config_surface",
            side_effect=MigrationLedgerError("the packaged ledger will not load"),
        )

        check = check_telemetry_config(config_dir=tmp_path)

        assert check.finding is TelemetryConfigFinding.INVALID
        assert "custom_posthog.mode" in check.message

    def test_check_telemetry_config_lets_an_unexpected_scan_bug_surface(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The catch is narrow on purpose: an applier bug is not a field condition."""
        (tmp_path / TELEMETRY_CONFIG_FILE_NAME).write_text('[custom_posthog]\nmode = "no-such-mode"\n', encoding="utf-8")
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.scan_config_surface",
            side_effect=RuntimeError("an applier bug"),
        )

        with pytest.raises(RuntimeError, match="an applier bug"):
            check_telemetry_config(config_dir=tmp_path)

    def test_check_telemetry_config_scans_only_the_directory_it_read(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The finding answers for the file on the row, not for the other tier beside it.

        A stale file in the global directory and a wrong one in the directory under inspection:
        reporting the first would send a `--global` reader to a migration that does nothing for
        the file they are looking at.
        """
        fake_home = tmp_path / "home"
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir(parents=True)
        (global_dir / TELEMETRY_CONFIG_FILE_NAME).write_text('telemetry_mode = "off"\n', encoding="utf-8")
        mocker.patch.object(Path, "home", return_value=fake_home)

        inspected = tmp_path / "inspected"
        inspected.mkdir()
        (inspected / TELEMETRY_CONFIG_FILE_NAME).write_text('[custom_posthog]\nmode = "no-such-mode"\n', encoding="utf-8")

        check = check_telemetry_config(config_dir=inspected)

        assert check.finding is TelemetryConfigFinding.INVALID
