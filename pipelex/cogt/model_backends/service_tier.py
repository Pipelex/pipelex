from enum import StrEnum


class ServiceTier(StrEnum):
    AUTO = "auto"
    DEFAULT = "default"
    FAST = "fast"
    FLEX = "flex"
    SCALE = "scale"
    PRIORITY = "priority"
    STANDARD_ONLY = "standard_only"
