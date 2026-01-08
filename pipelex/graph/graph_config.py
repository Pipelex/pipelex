from pipelex.graph.mermaidflow.mermaid_config import MermaidRenderingConfig
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.system.configuration.config_model import ConfigModel


class DataInclusionConfig(ConfigModel):
    """Controls which data is included in graph outputs."""

    stuff_json_content: bool
    stuff_text_content: bool
    stuff_html_content: bool
    error_stack_traces: bool


class GraphsInclusionConfig(ConfigModel):
    """Controls which graph outputs are generated."""

    graphspec_json: bool
    mermaidflow_mmd: bool
    mermaidflow_html: bool
    reactflow_viewspec: bool
    reactflow_html: bool


class GraphConfig(ConfigModel):
    """Configuration for graph tracing, storage, and rendering."""

    data_inclusion: DataInclusionConfig
    graphs_inclusion: GraphsInclusionConfig
    mermaid_config: MermaidRenderingConfig
    reactflow_config: ReactFlowRenderingConfig
