"""`runtime.log.package_log_levels` is a table of level names, and any other value is refused as a validation error.

A scalar here used to crash the config load with a bare `AttributeError` from a `mode="before"` validator
that called `.items()` on whatever it was given.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_levels import LogLevel
from tests.unit.pipelex.system.configuration.config_section_utils import base_config_section


class TestLogConfigPackageLogLevels:
    def test_level_names_are_converted_to_levels(self) -> None:
        log_config = LogConfig.model_validate({**base_config_section("runtime", "log"), "package_log_levels": {"pipelex": "DEBUG", "httpx": "INFO"}})

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
            LogConfig.model_validate({**base_config_section("runtime", "log"), "package_log_levels": value})

        assert exc_info.value.errors()[0]["loc"][0] == "package_log_levels"
