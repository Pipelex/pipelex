import logging

from pipelex.types import StrEnum

# custom logging level for development, between DEBUG and INFO
LOGGING_LEVEL_DEV = 15
LOGGING_LEVEL_DEV_NAME = "DEV"
logging.addLevelName(LOGGING_LEVEL_DEV, LOGGING_LEVEL_DEV_NAME)
# custom logging level for maximal verbosity, below DEBUG
LOGGING_LEVEL_VERBOSE = 5
LOGGING_LEVEL_VERBOSE_NAME = "VERBOSE"
logging.addLevelName(LOGGING_LEVEL_VERBOSE, LOGGING_LEVEL_VERBOSE_NAME)
LOGGING_LEVEL_OFF = 999


class LogLevel(StrEnum):
    VERBOSE = LOGGING_LEVEL_VERBOSE_NAME
    DEBUG = "DEBUG"
    DEV = LOGGING_LEVEL_DEV_NAME
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    OFF = "OFF"

    @property
    def int_logging_level(self) -> int:
        match self:
            case LogLevel.VERBOSE:
                return LOGGING_LEVEL_VERBOSE
            case LogLevel.DEBUG:
                return logging.DEBUG
            case LogLevel.DEV:
                return LOGGING_LEVEL_DEV
            case LogLevel.INFO:
                return logging.INFO
            case LogLevel.WARNING:
                return logging.WARNING
            case LogLevel.ERROR:
                return logging.ERROR
            case LogLevel.CRITICAL:
                return logging.CRITICAL
            case LogLevel.OFF:
                return LOGGING_LEVEL_OFF

    @staticmethod
    def from_int(logging_level: int) -> "LogLevel":
        if logging_level == LOGGING_LEVEL_VERBOSE:
            return LogLevel.VERBOSE
        elif logging_level == LOGGING_LEVEL_DEV:
            return LogLevel.DEV
        elif logging_level == LOGGING_LEVEL_OFF or logging_level > logging.CRITICAL:
            return LogLevel.OFF
        else:
            return LogLevel(logging.getLevelName(logging_level))
