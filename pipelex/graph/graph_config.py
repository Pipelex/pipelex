
from pydantic import field_validator

from pipelex.graph.mermaid_config import MermaidRenderingConfig
from pipelex.graph.reactflow_config import ReactFlowRenderingConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class DataInclusion(StrEnum):
    STUFF_JSON_CONTENT = "stuff_json_content"


class GraphConfig(ConfigModel):
    """Configuration for graph tracing, storage, and rendering."""

    max_preview_length: int
    max_stack_length: int
    data_inclusion: dict[DataInclusion, bool]
    mermaid_config: MermaidRenderingConfig
    reactflow_config: ReactFlowRenderingConfig

    @field_validator("data_inclusion", mode="before")
    @classmethod
    def validate_data_inclusion(cls, input_dict: dict[str, bool]) -> dict[DataInclusion, bool]:
        the_dict: dict[DataInclusion, bool] = {}
        for key, value in input_dict.items():
            the_dict[DataInclusion(key)] = value
        return the_dict
