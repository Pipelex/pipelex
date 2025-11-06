from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum

TELEMETRY_CONFIG_FILE_NAME = "telemetry.toml"


class TelemetryMode(StrEnum):
    ANONYMOUS = "anonymous"
    OFF = "off"
    IDENTIFIED = "identified"

    @property
    def is_enabled(self) -> bool:
        match self:
            case TelemetryMode.ANONYMOUS:
                return True
            case TelemetryMode.OFF:
                return False
            case TelemetryMode.IDENTIFIED:
                return True


class TelemetryConfig(ConfigModel):
    telemetry_mode: TelemetryMode = Field(strict=False)
    host: str
    project_api_key: str
    respect_dnt: bool
    redact: list[str]
    geoip_enabled: bool
    dry_mode_enabled: bool
    verbose_enabled: bool
    user_id: str
