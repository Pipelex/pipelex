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
        ("raw_level", "expected_enum"),
        [
            (LOGGING_LEVEL_VERBOSE, LogLevel.VERBOSE),
            (LOGGING_LEVEL_OFF, LogLevel.OFF),
            (logging.CRITICAL + 1, LogLevel.OFF),
            (logging.DEBUG, LogLevel.DEBUG),
            (logging.INFO, LogLevel.INFO),
        ],
    )
    def test_from_int_converts_to_enum(self, raw_level: int, expected_enum: LogLevel) -> None:
        assert LogLevel.from_int(logging_level=raw_level) == expected_enum

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

    def test_set_level_by_name_refuses_the_retired_dev_level(self) -> None:
        with pytest.raises(ValueError, match="DEV"):
            Log().set_level_by_name("DEV")
