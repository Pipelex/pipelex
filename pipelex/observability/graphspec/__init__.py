"""GraphSpec module for pipeline execution graph representation.

This module provides the canonical, versioned data model (GraphSpec) for
representing Pipelex pipeline execution graphs, along with JSON serialization,
validation utilities, a runtime tracer for building graphs during execution,
and exporters for Mermaid flowcharts and HTML visualization.
"""

from pipelex.observability.graphspec.exceptions import (
    GraphSpecError,
    GraphSpecValidationError,
    GraphSpecVersionError,
)
from pipelex.observability.graphspec.graph_context import GraphContext
from pipelex.observability.graphspec.graph_tracer import GraphTracer
from pipelex.observability.graphspec.graph_tracer_manager import (
    GraphTracerManager,
    GraphTracerManagerAbstract,
)
from pipelex.observability.graphspec.graph_tracer_protocol import (
    GraphTracerNoOp,
    GraphTracerProtocol,
)
from pipelex.observability.graphspec.graphspec import (
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
from pipelex.observability.graphspec.graphspec_io import (
    graphspec_from_json,
    graphspec_to_json,
    load_graphspec,
    save_graphspec,
)
from pipelex.observability.graphspec.html_renderer import render_mermaid_html
from pipelex.observability.graphspec.mermaid import graphspec_to_mermaid
from pipelex.observability.graphspec.validation import validate_graphspec

__all__ = [
    # Constants
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    # Enums
    "EdgeKind",
    "NodeKind",
    "NodeStatus",
    # Models
    "EdgeSpec",
    "ErrorSpec",
    "GraphContext",
    "GraphSpec",
    "IOSpec",
    "NodeIOSpec",
    "NodeSpec",
    "PipelineRef",
    "TimingSpec",
    # Tracer
    "GraphTracer",
    "GraphTracerManager",
    "GraphTracerManagerAbstract",
    "GraphTracerNoOp",
    "GraphTracerProtocol",
    # Exceptions
    "GraphSpecError",
    "GraphSpecValidationError",
    "GraphSpecVersionError",
    # I/O functions
    "graphspec_from_json",
    "graphspec_to_json",
    "load_graphspec",
    "save_graphspec",
    # Validation
    "validate_graphspec",
    # Mermaid/HTML export
    "graphspec_to_mermaid",
    "render_mermaid_html",
]
