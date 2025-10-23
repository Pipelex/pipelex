from typing import Any

from posthog import Posthog
from typing_extensions import override

from pipelex.system.environment import get_optional_env
from pipelex.system.telemetry.telemetry_config import TelemetryConfig, TelemetryMode
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.log import log

DO_NOT_TRACK_ENV_VAR_KEY = "DO_NOT_TRACK"


class TelemetryManager(TelemetryManagerAbstract):
    def __init__(self, telemetry_config: TelemetryConfig):
        self.do_not_track: bool
        if (dnt := get_optional_env(DO_NOT_TRACK_ENV_VAR_KEY)) and dnt.lower() not in ["false", "0"]:
            self.do_not_track = True
        else:
            self.do_not_track = False
        self.telemetry_config = telemetry_config
        self.posthog = Posthog(project_api_key=self.telemetry_config.project_api_key, host=self.telemetry_config.host)

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        pass

    @override
    def track_event(self, event_name: str, event_data: dict[str, Any] | None = None):
        if self.do_not_track:
            return
        # We copy the event data to avoid modifying the original dictionary
        if event_data:
            properties = event_data.copy()
        else:
            properties = {}
        for key in self.telemetry_config.redact:
            if key in self.telemetry_config.redact:
                properties.pop(key, None)
        match self.telemetry_config.telemetry_mode:
            case TelemetryMode.ANONYMOUS:
                self._track_anonymous_event(event_name=event_name, properties=properties)
            case TelemetryMode.IDENTIFIED:
                if not self.telemetry_config.user_id:
                    log.error(f"Could not track event '{event_name}' as identified because user_id is not set")
                    self._track_anonymous_event(event_name=event_name, properties=properties)
                else:
                    self._track_identified_event(event_name=event_name, properties=properties, user_id=self.telemetry_config.user_id)
            case TelemetryMode.OFF:
                log.dev(f"Telemetry is off, skipping event '{event_name}'")

    def _track_anonymous_event(self, event_name: str, properties: dict[str, Any]):
        if self.telemetry_config.debug:
            if properties:
                log.debug(properties, title=f"Tracking anonymous event '{event_name}'. properties")
            else:
                log.debug(f"Tracking anonymous event '{event_name}'. No properties.")
        else:
            properties["$process_person_profile"] = False
            self.posthog.capture(event_name, properties=properties)

    def _track_identified_event(self, event_name: str, properties: dict[str, Any], user_id: str):
        if self.telemetry_config.debug:
            if properties:
                log.debug(properties, title=f"Tracking identified event '{event_name}'. properties")
            else:
                log.debug(f"Tracking identified event '{event_name}'. No properties.")
        else:
            self.posthog.capture(event_name, distinct_id=user_id, properties=properties)
