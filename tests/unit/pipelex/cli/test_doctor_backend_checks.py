"""Unit tests for doctor's backend credential / backend file / kit template checks."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.cli.commands.doctor_cmd import (
    check_backend_credentials,
    check_backend_files,
    check_kit_template_exists,
    replace_backend_file,
)
from pipelex.cogt.exceptions import InferenceBackendLibraryError
from pipelex.kit.paths import get_kit_configs_dir

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

BACKENDS_TOML = """
[internal]
enabled = true

[openai]
enabled = true
api_key = "${TEST_DOCTOR_OPENAI_KEY}"

[azure]
enabled = false
api_key = "${TEST_DOCTOR_AZURE_KEY}"
"""


def _write_backends_toml(config_dir: Path, content: str = BACKENDS_TOML) -> Path:
    inference_dir = config_dir / "inference"
    inference_dir.mkdir(parents=True, exist_ok=True)
    backends_toml = inference_dir / "backends.toml"
    backends_toml.write_text(content, encoding="utf-8")
    return backends_toml


def _write_backends_override(config_dir: Path, content: str) -> Path:
    override = config_dir / "inference" / "backends_override.toml"
    override.write_text(content, encoding="utf-8")
    return override


class TestDoctorBackendChecks:
    def test_credentials_backends_toml_missing(self, tmp_path: Path) -> None:
        """No backends.toml means the credentials check fails with a clear message."""
        healthy, reports, message = check_backend_credentials(config_dir=tmp_path)

        assert healthy is False
        assert reports == {}
        assert message == "Backend configuration file not found"

    def test_credentials_all_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """All env vars set with real values is healthy; internal and disabled backends are skipped."""
        _write_backends_toml(tmp_path)
        monkeypatch.setenv("TEST_DOCTOR_OPENAI_KEY", "sk-real-value")
        monkeypatch.delenv("TEST_DOCTOR_AZURE_KEY", raising=False)

        healthy, reports, message = check_backend_credentials(config_dir=tmp_path)

        assert healthy is True
        assert set(reports.keys()) == {"openai"}
        assert reports["openai"].all_credentials_valid is True
        assert reports["openai"].required_vars == ["TEST_DOCTOR_OPENAI_KEY"]
        assert message == "All 1 enabled backend(s) have valid credentials"

    def test_credentials_missing_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unset env var is reported as missing for its backend."""
        _write_backends_toml(tmp_path)
        monkeypatch.delenv("TEST_DOCTOR_OPENAI_KEY", raising=False)

        healthy, reports, message = check_backend_credentials(config_dir=tmp_path)

        assert healthy is False
        assert reports["openai"].missing_vars == ["TEST_DOCTOR_OPENAI_KEY"]
        assert reports["openai"].all_credentials_valid is False
        assert message == "1 backend(s) have missing or invalid credentials"

    def test_credentials_placeholder_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An env var still holding a placeholder value is reported separately."""
        _write_backends_toml(tmp_path)
        monkeypatch.setenv("TEST_DOCTOR_OPENAI_KEY", "placeholder-for-TEST_DOCTOR_OPENAI_KEY")

        healthy, reports, _ = check_backend_credentials(config_dir=tmp_path)

        assert healthy is False
        assert reports["openai"].placeholder_vars == ["TEST_DOCTOR_OPENAI_KEY"]
        assert reports["openai"].missing_vars == []

    def test_credentials_broad_failure_reported(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Any unexpected failure during the scan becomes a finding, not a crash."""
        _write_backends_toml(tmp_path)
        mocker.patch("pipelex.cli.commands.doctor_cmd.load_toml_from_base_and_overrides", side_effect=RuntimeError("kaboom"))

        healthy, reports, message = check_backend_credentials(config_dir=tmp_path)

        assert healthy is False
        assert reports == {}
        assert message == "Error checking backend credentials: kaboom"

    def test_backend_files_no_backends_dir(self, tmp_path: Path) -> None:
        """A missing inference/backends directory is healthy (nothing to check)."""
        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert reports == {}
        assert message == "No backend files to check"

    def test_backend_files_no_backends_toml(self, tmp_path: Path) -> None:
        """A backends dir without backends.toml is healthy (nothing to check)."""
        (tmp_path / "inference" / "backends").mkdir(parents=True)

        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert reports == {}
        assert message == "No backends.toml to check"

    def test_backend_files_toml_error(self, tmp_path: Path) -> None:
        """An unparseable backends.toml fails the check with a load error."""
        _write_backends_toml(tmp_path, content="not [ valid toml")
        (tmp_path / "inference" / "backends").mkdir(parents=True)

        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is False
        assert reports == {}
        assert message.startswith("Error loading backends.toml:")

    def _setup_backend_file(self, tmp_path: Path) -> Path:
        _write_backends_toml(tmp_path)
        backends_dir = tmp_path / "inference" / "backends"
        backends_dir.mkdir(parents=True)
        backend_file = backends_dir / "openai.toml"
        backend_file.write_text("# openai backend specs\n", encoding="utf-8")
        return backend_file

    def test_backend_files_valid(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A backend file that loads cleanly is reported valid, with kit-template info."""
        self._setup_backend_file(tmp_path)
        library_mock = mocker.Mock()
        mocker.patch("pipelex.cli.commands.doctor_cmd.InferenceBackendLibrary.make_empty", return_value=library_mock)

        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert message == "All backend files are valid"
        assert reports["openai"].is_valid is True
        assert reports["openai"].error_message is None
        # openai ships in the kit, so the template is found by the real probe
        assert reports["openai"].has_kit_template is True

    def test_backend_files_library_error_naming_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A library error declaring the backend marks that file invalid."""
        self._setup_backend_file(tmp_path)
        library_mock = mocker.Mock()
        library_mock.load.side_effect = InferenceBackendLibraryError("invalid model spec", backend_name="openai")
        mocker.patch("pipelex.cli.commands.doctor_cmd.InferenceBackendLibrary.make_empty", return_value=library_mock)

        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is False
        assert message == "1 backend file(s) have validation errors"
        assert reports["openai"].is_valid is False
        assert reports["openai"].error_message == "invalid model spec"

    def test_backend_files_library_error_not_naming_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A library error that declares no backend and names no file leaves it valid."""
        self._setup_backend_file(tmp_path)
        library_mock = mocker.Mock()
        library_mock.load.side_effect = InferenceBackendLibraryError("some unrelated failure")
        mocker.patch("pipelex.cli.commands.doctor_cmd.InferenceBackendLibrary.make_empty", return_value=library_mock)

        healthy, reports, _ = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert reports["openai"].is_valid is True

    def test_backend_files_library_error_about_another_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """An error about another backend leaves this one valid, even when its prose mentions this one."""
        self._setup_backend_file(tmp_path)
        library_mock = mocker.Mock()
        library_mock.load.side_effect = InferenceBackendLibraryError(
            "Unknown key on model 'x' for backend 'anthropic': not an openai-style header", backend_name="anthropic"
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.InferenceBackendLibrary.make_empty", return_value=library_mock)

        healthy, reports, _ = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert reports["openai"].is_valid is True

    def _copy_kit_inference(self, tmp_path: Path) -> Path:
        """Provision the shipped defaults: the kit's whole inference/ tree, untouched."""
        shutil.copytree(Path(str(get_kit_configs_dir())) / "inference", tmp_path / "inference")
        return tmp_path / "inference" / "backends"

    def test_credentials_read_the_override_over_the_base(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A backend the personal override disables is not asked for credentials, and one it enables is."""
        _write_backends_toml(tmp_path)
        _write_backends_override(tmp_path, "[openai]\nenabled = false\n\n[azure]\nenabled = true\n")
        monkeypatch.delenv("TEST_DOCTOR_OPENAI_KEY", raising=False)
        monkeypatch.delenv("TEST_DOCTOR_AZURE_KEY", raising=False)

        healthy, reports, _ = check_backend_credentials(config_dir=tmp_path)

        assert healthy is False
        assert "openai" not in reports
        assert reports["azure"].missing_vars == ["TEST_DOCTOR_AZURE_KEY"]

    def test_backend_files_read_the_override_over_the_base(self, tmp_path: Path) -> None:
        """The file probe walks the merged document: a backend the override turns off is not probed,
        one it turns on is — and the loader it probes with is handed the same merged document.
        """
        self._copy_kit_inference(tmp_path)
        _write_backends_override(tmp_path, "[openai]\nenabled = false\n\n[vertexai]\nenabled = true\n")

        healthy, reports, _ = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert "openai" not in reports
        assert reports["vertexai"].is_valid is True

    def test_backend_files_stock_kit_is_healthy(self, tmp_path: Path) -> None:
        """The shipped defaults enable the gateway and ship its override file; the probe hands the
        loader no gateway config, and that must not be reported as a malformed file.
        """
        self._copy_kit_inference(tmp_path)

        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is True
        assert message == "All backend files are valid"
        assert reports["pipelex_gateway"].is_valid is True
        assert all(report.is_valid for report in reports.values())

    def test_backend_files_malformed_file_still_caught_under_leniency(self, tmp_path: Path) -> None:
        """Leniency skips the gateway, not a malformed file — and the gateway no longer hides one behind it."""
        backends_dir = self._copy_kit_inference(tmp_path)
        anthropic_file = backends_dir / "anthropic.toml"
        anthropic_file.write_text(anthropic_file.read_text(encoding="utf-8") + '\n[bogus_key_table]\nfoo = "bar"\n', encoding="utf-8")

        healthy, reports, message = check_backend_files(config_dir=tmp_path)

        assert healthy is False
        assert message == "1 backend file(s) have validation errors"
        assert reports["anthropic"].is_valid is False
        assert reports["anthropic"].error_message is not None
        assert "anthropic" in reports["anthropic"].error_message
        assert reports["pipelex_gateway"].is_valid is True

    def test_kit_template_exists_for_shipped_backend(self) -> None:
        """The kit ships an openai backend template."""
        assert check_kit_template_exists("openai") is True

    def test_kit_template_missing_for_unknown_backend(self) -> None:
        """An unknown backend has no kit template."""
        assert check_kit_template_exists("definitely_not_a_backend") is False

    def test_kit_template_lookup_failure_returns_false(self, mocker: MockerFixture) -> None:
        """A failing kit lookup degrades to 'no template'."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.get_kit_configs_dir", side_effect=RuntimeError("no kit"))

        assert check_kit_template_exists("openai") is False

    def test_replace_backend_file_writes_template(self, tmp_path: Path) -> None:
        """Replacing a backend file copies the kit template into the config dir."""
        success = replace_backend_file("openai", dry_run=False, config_dir=tmp_path)

        assert success is True
        target_file = tmp_path / "inference" / "backends" / "openai.toml"
        assert target_file.is_file()
        assert target_file.read_text(encoding="utf-8") != ""

    def test_replace_backend_file_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """Dry-run reports success without touching the filesystem."""
        success = replace_backend_file("openai", dry_run=True, config_dir=tmp_path)

        assert success is True
        assert not (tmp_path / "inference" / "backends" / "openai.toml").exists()

    def test_replace_backend_file_missing_template(self, tmp_path: Path) -> None:
        """A backend without a kit template cannot be replaced."""
        success = replace_backend_file("definitely_not_a_backend", dry_run=False, config_dir=tmp_path)

        assert success is False
