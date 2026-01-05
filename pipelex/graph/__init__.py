"""Graph module for Pipelex execution graphs.

This module provides:
- GraphSpec: Canonical graph representation
- GraphAnalysis: Pre-computed analysis for rendering
- ViewSpec: Viewer-oriented representation for ReactFlow
- Mermaid rendering functions
- ReactFlow HTML generation
"""

from pipelex.graph.graph_analysis import GraphAnalysis, StuffInfo
from pipelex.graph.graphspec import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    EdgeKind,
    EdgeSpec,
    ErrorSpec,
    GraphSpec,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
    TimingSpec,
)
from pipelex.graph.viewspec import (
    CURRENT_VIEWSPEC_VERSION,
    LayoutSpec,
    PayloadSpec,
    ViewEdge,
    ViewIndex,
    ViewNode,
    ViewSpec,
)

__all__ = [
    # GraphSpec
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "GraphSpec",
    "NodeSpec",
    "EdgeSpec",
    "NodeKind",
    "NodeStatus",
    "EdgeKind",
    "IOSpec",
    "NodeIOSpec",
    "TimingSpec",
    "ErrorSpec",
    "PipelineRef",
    # GraphAnalysis
    "GraphAnalysis",
    "StuffInfo",
    # ViewSpec
    "CURRENT_VIEWSPEC_VERSION",
    "ViewSpec",
    "ViewNode",
    "ViewEdge",
    "LayoutSpec",
    "ViewIndex",
    "PayloadSpec",
]
