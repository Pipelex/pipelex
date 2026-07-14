import logging

import pytest

from pipelex.tools.log.log_levels import (
    LOGGING_LEVEL_DEV,
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
            (LogLevel.DEV, LOGGING_LEVEL_DEV),
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
            (LOGGING_LEVEL_DEV, LogLevel.DEV),
            (LOGGING_LEVEL_OFF, LogLevel.OFF),
            (logging.CRITICAL + 1, LogLevel.OFF),
            (logging.DEBUG, LogLevel.DEBUG),
            (logging.INFO, LogLevel.INFO),
        ],
    )
    def test_from_int_converts_to_enum(self, raw_level: int, expected_enum: LogLevel) -> None:
        assert LogLevel.from_int(logging_level=raw_level) == expected_enum
