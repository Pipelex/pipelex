"""A `pipelex.toml` member of the wrong type is refused as a validation error, never crashed on or accepted silently.

Each model below used to convert or check a member in a `mode="before"` validator that assumed the raw
value's type: a scalar where a table was expected crashed the config load with a bare `AttributeError`,
a string where a list was expected was read as the set of its letters, and an invalid value was turned
into the default without a word.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.config_cogt import DryRunConfig
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.system.configuration.config_loader import CONFIG_NAME, ConfigLoader
from pipelex.system.configuration.configs import PipelexConfig, ScanConfig
from pipelex.system.exceptions import ConfigValidationError
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_levels import LogLevel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _base_config_section(*section_path: str) -> dict[str, Any]:
    """A section of the package's own `pipelex.toml`, the valid document each test spoils one member of."""
    section: dict[str, Any] = tomllib.loads((ConfigLoader().pipelex_root_dir / CONFIG_NAME).read_text(encoding="utf-8"))
    for key in section_path:
        section = section[key]
    return section


class TestLogConfigPackageLogLevels:
    def test_level_names_are_converted_to_levels(self) -> None:
        log_config = LogConfig.model_validate({**_base_config_section("runtime", "log"), "package_log_levels": {"pipelex": "DEBUG", "httpx": "INFO"}})

        assert log_config.package_log_levels == {"pipelex": LogLevel.DEBUG, "httpx": LogLevel.INFO}
        assert all(type(level) is LogLevel for level in log_config.package_log_levels.values())

    @pytest.mark.parametrize(
        ("value", "expected_fragment"),
        [
            pytest.param("x", "Input should be a valid dictionary", id="a_string"),
            pytest.param(["DEBUG"], "Input should be a valid dictionary", id="a_list"),
            pytest.param({"pipelex": "LOUD"}, "Input should be", id="an_unknown_level"),
        ],
    )
    def test_a_value_that_is_not_a_table_of_levels_is_refused(self, value: Any, expected_fragment: str) -> None:
        with pytest.raises(ValidationError, match=expected_fragment) as exc_info:
            LogConfig.model_validate({**_base_config_section("runtime", "log"), "package_log_levels": value})

        assert exc_info.value.errors()[0]["loc"][0] == "package_log_levels"


class TestScanConfigExcludedDirs:
    @pytest.mark.parametrize("value", [["node_modules", ".venv"], ("node_modules", ".venv"), frozenset({"node_modules", ".venv"})])
    def test_a_list_of_names_is_read_as_a_set(self, value: Any) -> None:
        assert ScanConfig.model_validate({"excluded_dirs": value}).excluded_dirs == frozenset({"node_modules", ".venv"})

    @pytest.mark.parametrize("value", [pytest.param("node_modules", id="a_string"), pytest.param(5, id="an_integer")])
    def test_a_value_that_is_not_a_list_is_refused(self, value: Any) -> None:
        with pytest.raises(ValidationError, match="Input should be a valid frozenset"):
            ScanConfig.model_validate({"excluded_dirs": value})


class TestDryRunConfigImageUrls:
    def test_an_empty_list_is_a_validation_error(self) -> None:
        """It used to raise a bare `PipelexConfigError` from inside the validator, which escaped the config load's wrap."""
        with pytest.raises(ValidationError, match=r"inference\.dry_run\.image_urls must be a non-empty list"):
            DryRunConfig.model_validate({**_base_config_section("inference", "dry_run"), "image_urls": []})

    def test_a_string_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Input should be a valid list"):
            DryRunConfig.model_validate({**_base_config_section("inference", "dry_run"), "image_urls": "https://example.com/a.png"})


class TestLLMSettingMaxTokens:
    @pytest.mark.parametrize(("value", "expected"), [(None, None), ("auto", None), (4096, 4096)])
    def test_none_auto_and_an_integer_are_accepted(self, value: Any, expected: int | None) -> None:
        assert LLMSetting.model_validate({"model": "test-model", "temperature": 0.5, "max_tokens": value}).max_tokens == expected

    @pytest.mark.parametrize(
        "value",
        [pytest.param("foo", id="a_string"), pytest.param(3.5, id="a_float"), pytest.param(True, id="a_boolean")],
    )
    def test_any_other_value_is_refused_rather_than_read_as_the_default(self, value: Any) -> None:
        with pytest.raises(ValidationError) as exc_info:
            LLMSetting.model_validate({"model": "test-model", "temperature": 0.5, "max_tokens": value})

        assert exc_info.value.errors()[0]["loc"][0] == "max_tokens"


@pytest.mark.usefixtures("no_pipelex_home")
class TestTheConfigLoadReportsAWrongTypedMember:
    def test_a_project_file_with_a_scalar_package_log_levels_fails_the_load_with_the_loaders_error(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The boot catches the loader's `ConfigValidationError`; a bare `AttributeError` used to escape it."""
        fake_home = tmp_path / "home"
        (fake_home / ".pipelex").mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        (project_root / ".pipelex").mkdir()
        (project_root / ".pipelex" / CONFIG_NAME).write_text('[runtime.log]\npackage_log_levels = "x"\n', encoding="utf-8")
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        with pytest.raises(ConfigValidationError, match="package_log_levels"):
            ConfigLoader().load_config_validated(config_cls=PipelexConfig)
