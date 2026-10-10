import os

import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.system.environment import get_positive_int_env

ENV_VAR = "PIPELEX_MAX_FETCHED_PACKAGE_FILES"


class TestPositiveIntEnv:
    @pytest.mark.parametrize("raw", ["many", "0", "-3", "2.5"])
    def test_a_value_that_is_no_positive_integer_falls_back_naming_the_variable(self, mocker: MockerFixture, raw: str) -> None:
        """An unparseable and a non-positive value fall back alike, and the line names the variable and the default, never the value."""
        mocker.patch.dict(os.environ, {ENV_VAR: raw})
        warning_spy = mocker.patch.object(log, "warning")

        assert get_positive_int_env(env_var=ENV_VAR, default=256) == 256

        warning_spy.assert_called_once_with(
            "An environment variable holds no positive integer, so its default applies",
            fields={"env_var": ENV_VAR, "default_value": 256},
        )

    @pytest.mark.parametrize(("raw", "expected"), [("12", 12), (None, 256), ("", 256)], ids=["positive", "unset", "empty"])
    def test_a_positive_integer_or_no_value_is_read_silently(self, mocker: MockerFixture, raw: str | None, expected: int) -> None:
        environment = {key: value for key, value in os.environ.items() if key != ENV_VAR}
        if raw is not None:
            environment[ENV_VAR] = raw
        mocker.patch.dict(os.environ, environment, clear=True)
        warning_spy = mocker.patch.object(log, "warning")

        assert get_positive_int_env(env_var=ENV_VAR, default=256) == expected

        warning_spy.assert_not_called()
