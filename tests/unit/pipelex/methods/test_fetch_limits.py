import pytest
from pytest_mock import MockerFixture

from pipelex.methods.fetch_limits import _read_positive_int  # pyright: ignore[reportPrivateUsage]

ENV_VAR = "PIPELEX_MAX_FETCHED_PACKAGE_FILES"


class TestFetchLimits:
    @pytest.mark.parametrize("raw", ["many", "0", "-3"])
    def test_a_value_that_is_no_positive_integer_falls_back_naming_the_variable(self, mocker: MockerFixture, raw: str) -> None:
        """An unparseable and a non-positive value fall back alike, and the line names the variable and the default, never the value."""
        mocker.patch("pipelex.methods.fetch_limits.get_optional_env", return_value=raw)
        warning_mock = mocker.patch("pipelex.methods.fetch_limits.log.warning")

        assert _read_positive_int(env_var=ENV_VAR, default=256) == 256

        warning_mock.assert_called_once_with(
            "An environment variable holds no positive integer, so the default ceiling applies",
            fields={"env_var": ENV_VAR, "default_value": 256},
        )

    def test_a_positive_integer_is_read_silently(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.methods.fetch_limits.get_optional_env", return_value="12")
        warning_mock = mocker.patch("pipelex.methods.fetch_limits.log.warning")

        assert _read_positive_int(env_var=ENV_VAR, default=256) == 12

        warning_mock.assert_not_called()
