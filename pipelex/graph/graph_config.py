from pipelex.graph.mermaidflow.mermaid_config import MermaidRenderingConfig
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.data_inclusion_config import DataInclusionConfig


class GraphsInclusionConfig(ConfigModel):
    """Controls which graph outputs are generated."""

    graphspec_json: bool
    mermaidflow_mmd: bool
    mermaidflow_html: bool
    reactflow_html: bool


class GraphConfig(ConfigModel):
    """Configuration for graph tracing, storage, and rendering."""

    data_inclusion: DataInclusionConfig
    graphs_inclusion: GraphsInclusionConfig
    mermaid: MermaidRenderingConfig
    reactflow: ReactFlowRenderingConfig
