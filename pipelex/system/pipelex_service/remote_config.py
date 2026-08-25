from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs


class PipelexPosthogConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_api_key: str = Field(description="Posthog project API key")
    endpoint: str = Field(description="Posthog endpoint URL")
    is_geoip_enabled: bool = Field(description="Enable GeoIP lookup")
    is_debug_enabled: bool = Field(description="Enable PostHog debug mode")


class RemoteConfig(BaseModel):
    """The single artifact the Pipelex service publishes, carrying one model-specs section per managed gateway.

    `backend_model_specs` is the legacy gateway's section and stays a declared field. Every other
    section — `manifold_model_specs` today — arrives through `extra="allow"`, which is what makes
    adding one a non-breaking change for a client that predates it: an older runtime parses the
    artifact and simply never asks for the new section.
    """

    model_config = ConfigDict(extra="allow")

    posthog: PipelexPosthogConfig = Field(description="Posthog configuration")
    backend_model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")
    aws_region: str = Field(description="AWS region")

    def get_model_specs_section(self, section_name: str) -> BackendModelSpecs | None:
        """The named model-specs section, or ``None`` when the artifact does not carry one.

        Looked up by name rather than by field, because which section a managed backend reads is
        declared in that backend's configuration and the runtime learns it at boot. ``None`` is a
        real answer and not an error here: a backend declaring a section the published artifact does
        not carry is disabled with a named warning, the same posture as a missing variable.
        """
        raw = getattr(self, section_name, None)
        if not isinstance(raw, dict):
            return None
        return cast("BackendModelSpecs", raw)
