"""Types for the init command UI."""

from pipelex.types import StrEnum


class InitFocus(StrEnum):
    """Focus options for initialization."""

    ALL = "all"
    AGREEMENT = "agreement"
    CONFIG = "config"
    CREDENTIALS = "credentials"
    INFERENCE = "inference"
    ROUTING = "routing"
    TELEMETRY = "telemetry"
