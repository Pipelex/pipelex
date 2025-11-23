from typing import cast

import pytest

from pipelex.tools.log.log_config import CallerInfoTemplate, LogConfig
from pipelex.tools.log.log_levels import LogLevel


class TestLogConfigUtilities:
    @pytest.mark.parametrize(
        ("template_key", "expected_template"),
        [
            (CallerInfoTemplate.FILE_LINE, "{file}:{line}"),
            (CallerInfoTemplate.FILE_LINE_FUNC, "{file}:{line} {func}"),
            (CallerInfoTemplate.FUNC, "{func}"),
            (CallerInfoTemplate.FILE_FUNC, "{file} {func}"),
            (CallerInfoTemplate.FUNC_LINE, "{func} {line}"),
            (CallerInfoTemplate.FUNC_MODULE, "{func} {module}"),
            (CallerInfoTemplate.FUNC_MODULE_LINE, "{func} {module} {line}"),
        ],
    )
    def test_caller_info_template_mapping(self, template_key: CallerInfoTemplate, expected_template: str) -> None:
        assert CallerInfoTemplate.for_template_key(template_key) == expected_template

    def test_caller_info_template_returns_empty_string_for_unknown_key(self) -> None:
        unknown_key = cast("CallerInfoTemplate", None)

        assert CallerInfoTemplate.for_template_key(unknown_key) == ""

    def test_validate_package_log_levels_converts_strings_to_enum(self) -> None:
        package_levels = {"pipelex": "DEBUG", "pipelex.tools": "INFO"}

        validated_levels = LogConfig.validate_package_log_levels(package_levels)

        assert validated_levels == {
            "pipelex": LogLevel.DEBUG,
            "pipelex.tools": LogLevel.INFO,
        }
