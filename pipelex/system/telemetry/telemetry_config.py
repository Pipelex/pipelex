from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class TelemetryMode(StrEnum):
    OFF = "off"
    ANONYMOUS = "anonymous"
    IDENTIFIED = "identified"


class TelemetryConfig(ConfigModel):
    settings_customized: bool
    telemetry_mode: TelemetryMode = Field(strict=False)
    host: str
    project_api_key: str
    respect_dnt: bool
    redact: list[str]
    debug: bool
    user_id: str
