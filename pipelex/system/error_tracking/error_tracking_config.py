"""`[runtime.error_tracking]`: which error trackers a process reports the errors it meets to."""

from enum import StrEnum

from pydantic import field_validator

from pipelex.system.configuration.config_model import ConfigModel


class ErrorTrackerMethod(StrEnum):
    """The error trackers Pipelex ships. ``runtime.error_tracking.trackers`` is an open list: a plugin adds its own token."""

    POSTHOG = "posthog"


class ErrorTrackingConfig(ConfigModel):
    """`[runtime.error_tracking]`: the error trackers boot installs, each named by the token its plugin registered.

    Attributes:
        trackers: The tokens of the trackers to install, in the order each report reaches them. An empty list installs
            none, and pipelex reports nothing beyond its log lines. A token is validated at boot, by the registry
            lookup, not here, so a token an external plugin provides parses whether or not that plugin is installed.
    """

    trackers: list[str]

    @field_validator("trackers")
    @classmethod
    def _refuse_a_repeated_tracker(cls, value: list[str]) -> list[str]:
        repeated = sorted({token for token in value if value.count(token) > 1})
        if repeated:
            msg = f"runtime.error_tracking.trackers names a tracker more than once: {', '.join(repeated)}"
            raise ValueError(msg)
        return value
