from importlib.metadata import metadata
from typing import Any

from posthog import Posthog, new_context, tag
from typing_extensions import override

from pipelex.system.telemetry.events import EventName, EventProperty, Setting
from pipelex.system.telemetry.telemetry_config import TelemetryConfig, TelemetryIntegration, TelemetryMode
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.log import log

DO_NOT_TRACK_ENV_VAR_KEY = "DO_NOT_TRACK"
PACKAGE_NAME = __name__.split(".", maxsplit=1)[0]
PACKAGE_VERSION = metadata(PACKAGE_NAME)["Version"]


class TelemetryManager(TelemetryManagerAbstract):
    def __init__(self, telemetry_config: TelemetryConfig):
        self.telemetry_config = telemetry_config
        self.posthog = Posthog(
            project_api_key=self.telemetry_config.project_api_key,
            host=self.telemetry_config.host,
            disable_geoip=not self.telemetry_config.geoip_enabled,
            debug=self.telemetry_config.verbose_enabled,
        )

    @override
    def setup(self):
        if telemetry_mode := TelemetryManagerAbstract.telemetry_was_just_enabled():
            with new_context():
                tag(name=EventProperty.INTEGRATION, value=TelemetryIntegration.CLI)
                tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
                tag(name=EventProperty.SETTING, value=Setting.TELEMETRY_MODE)
            self.posthog.capture(
                EventName.TELEMETRY_JUST_ENABLED,
                properties={
                    EventProperty.TELEMETRY_MODE: telemetry_mode,
                    EventProperty.PIPELEX_VERSION: PACKAGE_VERSION,
                },
            )

    @override
    def teardown(self):
        pass

    @override
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        # We copy the incoming properties to avoid modifying the original dictionary
        # and to convert the keys to str
        # and to remove the properties that are in the redact list
        tracked_properties: dict[str, Any]
        if properties:
            tracked_properties = {key: value for key, value in properties.items() if key not in self.telemetry_config.redact}
        else:
            tracked_properties = {}
        match self.telemetry_config.telemetry_mode:
            case TelemetryMode.ANONYMOUS:
                self._track_anonymous_event(event_name=event_name, properties=tracked_properties)
            case TelemetryMode.IDENTIFIED:
                if not self.telemetry_config.user_id:
                    log.error(f"Could not track event '{event_name}' as identified because user_id is not set, tracking as anonymous")
                    self._track_anonymous_event(event_name=event_name, properties=tracked_properties)
                else:
                    self._track_identified_event(event_name=event_name, properties=tracked_properties, user_id=self.telemetry_config.user_id)
            case TelemetryMode.OFF:
                log.verbose(f"Telemetry is off, skipping event '{event_name}'")

    def _track_anonymous_event(self, event_name: str, properties: dict[str, Any]):
        if not self.posthog:
            return
        if self.telemetry_config.dry_mode_enabled:
            if properties:
                log.debug(properties, title=f"Tracking anonymous event '{event_name}'. Properties")
            else:
                log.debug(f"Tracking anonymous event '{event_name}'. No properties.")
        else:
            properties["$process_person_profile"] = False
            self.posthog.capture(event_name, properties=properties)
            log.verbose(f"Tracked anonymous event '{event_name}' with properties: {properties}")

    def _track_identified_event(self, event_name: str, properties: dict[str, Any], user_id: str):
        if not self.posthog:
            return
        if self.telemetry_config.dry_mode_enabled:
            if properties:
                log.debug(properties, title=f"Tracking identified event '{event_name}'. Properties")
            else:
                log.debug(f"Tracking identified event '{event_name}'. No properties.")
        else:
            self.posthog.capture(event_name, distinct_id=user_id, properties=properties)
            log.verbose(f"Tracked identified event '{event_name}' with properties: {properties}")
