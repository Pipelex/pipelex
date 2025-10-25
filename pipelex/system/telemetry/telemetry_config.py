from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class TelemetryMode(StrEnum):
    OFF = "off"
    ANONYMOUS = "anonymous"
    IDENTIFIED = "identified"


class TelemetryIntegration(StrEnum):
    CLI = "cli"
    FASTAPI = "fastapi"
    DOCKER = "docker"
    MCP = "mcp"
    N8N = "n8n"
    PYTHON = "python"
    PYTEST = "pytest"


class TelemetryConfig(ConfigModel):
    settings_customized: bool
    integration: TelemetryIntegration | None = Field(default=None, strict=False)
    telemetry_mode: TelemetryMode = Field(strict=False)
    host: str
    project_api_key: str
    respect_dnt: bool
    redact: list[str]
    geoip_enabled: bool
    dry_mode_enabled: bool
    verbose_enabled: bool
    user_id: str
