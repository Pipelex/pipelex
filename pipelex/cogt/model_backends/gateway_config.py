from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")
    aws_region: str = Field(description="AWS region")
