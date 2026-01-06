"""Shared fixtures for graph unit tests."""

import pytest

from pipelex.graph.graph_config import DataInclusionConfig, GraphConfig, GraphsInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.mermaid_config import MermaidRenderingConfig, MermaidStyle, MermaidTheme
from pipelex.graph.reactflow_config import ReactFlowRenderingConfig, ReactFlowStyle, ReactFlowTheme
from pipelex.tools.misc.chart_utils import FlowchartDirection


def make_defaulted_data_inclusion_config(
    stuff_json_content: bool = False,
    stuff_text_content: bool = False,
    stuff_html_content: bool = False,
) -> DataInclusionConfig:
    """Create a DataInclusionConfig for testing.

    Args:
        stuff_json_content: Whether to include JSON stuff data.
        stuff_text_content: Whether to include plain text stuff data.
        stuff_html_content: Whether to include HTML stuff data.

    Returns:
        A DataInclusionConfig configured for testing.
    """
    return DataInclusionConfig(
        stuff_json_content=stuff_json_content,
        stuff_text_content=stuff_text_content,
        stuff_html_content=stuff_html_content,
    )


def make_graph_context(
    graph_id: str = "test-graph",
    parent_node_id: str | None = None,
    node_sequence: int = 0,
    stuff_json_content: bool = False,
    stuff_text_content: bool = False,
    stuff_html_content: bool = False,
) -> GraphContext:
    """Create a GraphContext for testing.

    Args:
        graph_id: The graph identifier.
        parent_node_id: Optional parent node ID.
        node_sequence: The node sequence counter.
        stuff_json_content: Whether to include JSON stuff data.
        stuff_text_content: Whether to include plain text stuff data.
        stuff_html_content: Whether to include HTML stuff data.

    Returns:
        A GraphContext configured for testing.
    """
    return GraphContext(
        graph_id=graph_id,
        parent_node_id=parent_node_id,
        node_sequence=node_sequence,
        data_inclusion=make_defaulted_data_inclusion_config(
            stuff_json_content=stuff_json_content,
            stuff_text_content=stuff_text_content,
            stuff_html_content=stuff_html_content,
        ),
    )


@pytest.fixture
def data_inclusion_config() -> DataInclusionConfig:
    """Fixture that provides a default DataInclusionConfig for testing."""
    return make_defaulted_data_inclusion_config()


def make_graph_config(
    include_stuff_json: bool = False,
    include_stuff_text: bool = False,
    include_stuff_html: bool = False,
) -> GraphConfig:
    """Create a GraphConfig for testing.

    Args:
        include_stuff_json: Whether to include JSON stuff data.
        include_stuff_text: Whether to include plain text stuff data.
        include_stuff_html: Whether to include HTML stuff data.

    Returns:
        A GraphConfig configured for testing.
    """
    return GraphConfig(
        data_inclusion=DataInclusionConfig(
            stuff_json_content=include_stuff_json,
            stuff_text_content=include_stuff_text,
            stuff_html_content=include_stuff_html,
        ),
        graphs_inclusion=GraphsInclusionConfig(
            graphspec_json=True,
            orchestration_mmd=True,
            orchestration_html=True,
            dataflow_mmd=True,
            dataflow_html=True,
            combo_mmd=True,
            combo_html=True,
            reactflow_viewspec=True,
            reactflow_html=True,
        ),
        mermaid_config=MermaidRenderingConfig(
            direction=FlowchartDirection.TOP_DOWN,
            is_include_data_edges=True,
            is_include_contains_edges=False,
            is_include_selected_outcome_edges=True,
            is_show_stuff_codes=False,
            style=MermaidStyle(theme=MermaidTheme.LIGHT),
        ),
        reactflow_config=ReactFlowRenderingConfig(
            is_use_cdn=True,
            layout_direction="TB",
            nodesep=50,
            ranksep=80,
            default_title="Test Graph",
            style=ReactFlowStyle(theme=ReactFlowTheme.DARK),
        ),
    )


@pytest.fixture
def graph_config() -> GraphConfig:
    """Fixture that provides a default GraphConfig for testing."""
    return make_graph_config()


@pytest.fixture
def graph_config_with_json_data() -> GraphConfig:
    """Fixture that provides a GraphConfig with JSON stuff data enabled."""
    return make_graph_config(include_stuff_json=True)


@pytest.fixture
def graph_config_with_all_data() -> GraphConfig:
    """Fixture that provides a GraphConfig with all stuff data formats enabled."""
    return make_graph_config(include_stuff_json=True, include_stuff_text=True, include_stuff_html=True)
