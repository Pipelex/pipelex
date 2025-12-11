from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs


class PipelexPosthogConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_api_key: str = Field(description="Posthog project API key")
    endpoint: str = Field(description="Posthog endpoint URL")
    is_geoip_enabled: bool = Field(description="Enable GeoIP lookup")
    is_debug_enabled: bool = Field(description="Enable PostHog debug mode")


class RemoteConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    posthog: PipelexPosthogConfig = Field(description="Posthog configuration")
    backend_model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")
