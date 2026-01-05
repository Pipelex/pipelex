from pydantic import field_validator

from pipelex.graph.mermaid_config import MermaidRenderingConfig
from pipelex.graph.reactflow_config import ReactFlowRenderingConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class DataInclusion(StrEnum):
    STUFF_JSON_CONTENT = "stuff_json_content"


class GraphsInclusion(StrEnum):
    """Controls which graph outputs are generated."""

    GRAPHSPEC_JSON = "graphspec_json"
    ORCHESTRATION_MMD = "orchestration_mmd"
    ORCHESTRATION_HTML = "orchestration_html"
    DATAFLOW_MMD = "dataflow_mmd"
    DATAFLOW_HTML = "dataflow_html"
    COMBO_MMD = "combo_mmd"
    COMBO_HTML = "combo_html"
    REACTFLOW_VIEWSPEC = "reactflow_viewspec"
    REACTFLOW_HTML = "reactflow_html"


class GraphConfig(ConfigModel):
    """Configuration for graph tracing, storage, and rendering."""

    max_preview_length: int
    max_stack_length: int
    data_inclusion: dict[DataInclusion, bool]
    graphs_inclusion: dict[GraphsInclusion, bool]
    mermaid_config: MermaidRenderingConfig
    reactflow_config: ReactFlowRenderingConfig

    @field_validator("data_inclusion", mode="before")
    @classmethod
    def validate_data_inclusion(cls, input_dict: dict[str, bool]) -> dict[DataInclusion, bool]:
        the_dict: dict[DataInclusion, bool] = {}
        for key, value in input_dict.items():
            the_dict[DataInclusion(key)] = value
        return the_dict

    @field_validator("graphs_inclusion", mode="before")
    @classmethod
    def validate_graphs_inclusion(cls, input_dict: dict[str, bool]) -> dict[GraphsInclusion, bool]:
        the_dict: dict[GraphsInclusion, bool] = {}
        for key, value in input_dict.items():
            the_dict[GraphsInclusion(key)] = value
        return the_dict
