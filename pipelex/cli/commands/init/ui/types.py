"""Types for the init command UI."""

from enum import StrEnum


class InitFocus(StrEnum):
    """Focus options for initialization."""

    ALL = "all"
    CONFIG = "config"
    CREDENTIALS = "credentials"
    INFERENCE = "inference"
    ROUTING = "routing"
    TELEMETRY = "telemetry"
