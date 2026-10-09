import logging

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.log.log import Log
from pipelex.tools.log.log_levels import (
    LOGGING_LEVEL_OFF,
    LOGGING_LEVEL_VERBOSE,
    LogLevel,
)


class TestLogLevels:
    @pytest.mark.parametrize(
        ("log_level", "expected_int_level"),
        [
            (LogLevel.VERBOSE, LOGGING_LEVEL_VERBOSE),
            (LogLevel.DEBUG, logging.DEBUG),
            (LogLevel.INFO, logging.INFO),
            (LogLevel.WARNING, logging.WARNING),
            (LogLevel.ERROR, logging.ERROR),
            (LogLevel.CRITICAL, logging.CRITICAL),
            (LogLevel.OFF, LOGGING_LEVEL_OFF),
        ],
    )
    def test_int_logging_level_returns_correct_value(self, log_level: LogLevel, expected_int_level: int) -> None:
        assert log_level.int_logging_level == expected_int_level

    @pytest.mark.parametrize(
        ("level_name", "expected_int_level"),
        [
            ("verbose", LOGGING_LEVEL_VERBOSE),
            ("DEBUG", logging.DEBUG),
            ("Off", LOGGING_LEVEL_OFF),
        ],
    )
    def test_set_level_by_name_takes_a_member_name_in_any_case(self, mocker: MockerFixture, level_name: str, expected_int_level: int) -> None:
        fresh = Log()
        set_level_by_int = mocker.patch.object(fresh, "set_level_by_int")

        fresh.set_level_by_name(level_name)

        set_level_by_int.assert_called_once_with(level_int=expected_int_level)

    @pytest.mark.parametrize("level_name", ["DEV", "WARN", "FATAL", "NOTSET"])
    def test_set_level_by_name_refuses_a_name_that_is_no_level(self, level_name: str) -> None:
        """The retired `DEV` and the stdlib-only spellings alike: only a `LogLevel` name is a level here."""
        with pytest.raises(ValueError, match=level_name):
            Log().set_level_by_name(level_name)
