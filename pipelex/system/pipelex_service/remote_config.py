from pydantic import BaseModel, Field

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs


class PosthogConfig(BaseModel):
    project_api_key: str = Field(description="Posthog project API key")
    host: str = Field(description="Posthog host")


class RemoteConfig(BaseModel):
    backend_model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")
    posthog: PosthogConfig = Field(description="Posthog configuration")
