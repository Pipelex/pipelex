"""Types for the init command UI."""

from pipelex.types import StrEnum


class InitFocus(StrEnum):
    """Focus options for initialization."""

    ALL = "all"
    CONFIG = "config"
    INFERENCE = "inference"
    ROUTING = "routing"
    TELEMETRY = "telemetry"
