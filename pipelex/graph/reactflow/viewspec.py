"""ViewSpec Pydantic v2 models for ReactFlow and other interactive graph viewers.

This module defines viewer-oriented, derived models that sit on top of GraphSpec
and answer: "What should the UI render, and how?" ViewSpec is safe to regenerate
at any time from GraphSpec + viewer/CLI options.

ViewSpec is renderer-specific enough to be convenient (ReactFlow types, handles,
layout params), but still broadly usable for other interactive renderers later.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

# Current ViewSpec schema version (independent of GraphSpec version)
CURRENT_VIEWSPEC_VERSION = "1.0"

ViewEngine = Literal["reactflow"]
LayoutEngine = Literal["dagre"]
LayoutDirection = Literal["TB", "LR", "BT", "RL"]


class LayoutSpec(BaseModel):
    """Layout configuration for graph rendering.

    Specifies how the graph should be laid out, typically using Dagre.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    engine: LayoutEngine = "dagre"
    direction: LayoutDirection = "TB"
    nodesep: int | None = 50
    ranksep: int | None = 80
    align: str | None = None
    allow_manual_positions: bool = True


class ViewNode(BaseModel):
    """ReactFlow node representation.

    Maps a GraphSpec node to a ReactFlow-compatible node with UI metadata,
    inspector data, and optional position/size.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(description="GraphSpec node_id - must match exactly for cross-referencing")
    label: str = Field(description="Display label for the node")
    kind: str = Field(description="Copy or normalize GraphSpec.kind")
    status: str | None = Field(default=None, description="Copy GraphSpec.status when relevant")

    # ReactFlow-specific
    type: str = Field(default="default", description='ReactFlow node type, e.g. "operator", "controller", "io", "error", "artifact"')
    parent_id: str | None = Field(default=None, description="Parent node ID for grouping/containment in UI")
    extent: Literal["parent"] | None = Field(default=None, description="ReactFlow grouping behavior (optional)")

    # Optional persisted position (viewer will compute with Dagre if absent)
    position: dict[str, float] | None = Field(default=None, description='Optional position dict: {"x": ..., "y": ...}')
    size: dict[str, float] | None = Field(default=None, description='Optional size dict: {"width": ..., "height": ...}')

    # Small UI metadata (avoid heavy data here)
    ui: dict[str, Any] = Field(default_factory=dict, description='UI metadata, e.g. {"badges": ["132ms"], "classes": ["ok"], "icon": "llm"}')

    # What the inspector needs quickly (lightweight)
    inspector: dict[str, Any] = Field(
        default_factory=dict,
        description='Inspector data, e.g. {"pipe_code": "...", "pipe_type": "...", "timing": {...}, "io_preview": {...}, "error": {...}}',
    )

    # Optional handle definitions if you later do port-specific edges
    handles: list[dict[str, Any]] | None = Field(
        default=None,
        description='Optional handles, e.g. [{"id": "out.cv_pages", "type": "source", "position": "Right"}]',
    )


class ViewEdge(BaseModel):
    """ReactFlow edge representation.

    Maps a GraphSpec edge to a ReactFlow-compatible edge with type, animation,
    and optional handles.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(description="GraphSpec edge_id - must match exactly for cross-referencing")
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    kind: str = Field(description="Copy GraphSpec.kind")
    label: str | None = Field(default=None, description="Edge label if present")

    # ReactFlow-specific
    type: str = Field(default="default", description='ReactFlow edge type, e.g. "data", "control", "contains"')
    animated: bool | None = Field(default=None, description="Whether the edge should be animated")
    hidden: bool = Field(default=False, description="Whether the edge should be hidden")

    source_handle: str | None = Field(default=None, description="Source handle ID for port-specific edges")
    target_handle: str | None = Field(default=None, description="Target handle ID for port-specific edges")

    ui: dict[str, Any] = Field(default_factory=dict, description='UI metadata, e.g. {"classes": ["dashed"], "markerEnd": "arrow"}')


class ViewIndex(BaseModel):
    """Optional performance indexes for fast lookups in the viewer.

    These indexes avoid expensive client-side recomputation.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    edges_by_node: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of node_id to list of edge_ids connected to that node",
    )
    children_by_parent: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of parent node_id to list of child node_ids",
    )
    search: dict[str, list[str]] = Field(
        default_factory=dict,
        description='Search index, e.g. {"pipe_code:extract_text": ["nodeA"], "status:failed": ["nodeZ"]}',
    )


class PayloadSpec(BaseModel):
    """Optional external payload strategy for large graphs.

    Allows lazy-loading of full I/O data instead of embedding everything inline.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["inline", "external"] = "inline"
    base_path: str | None = Field(default=None, description="Base path for external payload files")
    by_digest: dict[str, str] = Field(
        default_factory=dict,
        description="Map of digest to relative file path for lazy-loading",
    )


class ViewSpec(BaseModel):
    """Viewer-oriented, derived layer for graph rendering.

    ViewSpec sits on top of GraphSpec and answers: "What should the UI render, and how?"
    It is safe to regenerate at any time from GraphSpec + viewer/CLI options.

    ViewSpec is renderer-specific enough to be convenient (ReactFlow types, handles,
    layout params), but still broadly usable for other interactive renderers later.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str = Field(default=CURRENT_VIEWSPEC_VERSION, description="ViewSpec schema version (independent of GraphSpec version)")
    created_at: datetime = Field(description="When this ViewSpec was created")
    graph_id: str = Field(description="Must match GraphSpec.graph_id for cross-referencing")
    source: dict[str, Any] = Field(
        default_factory=dict,
        description='Source metadata, e.g. {"graph_schema_version": "1.0", "graph_digest": "sha256:...", "producer": "pipelex 0.9.3"}',
    )

    engine: ViewEngine = Field(default="reactflow", description="View engine identifier")

    # Global toggles applied to build this view
    options: dict[str, Any] = Field(
        default_factory=dict,
        description='View options, e.g. {"show_data_edges": True, "collapse_controllers": False, "redaction": "preview-only"}',
    )

    layout: LayoutSpec = Field(default_factory=LayoutSpec, description="Layout configuration")

    nodes: list[ViewNode] = Field(default_factory=empty_list_factory_of(ViewNode), description="List of view nodes")
    edges: list[ViewEdge] = Field(default_factory=empty_list_factory_of(ViewEdge), description="List of view edges")

    # Optional accelerators
    index: ViewIndex | None = Field(default=None, description="Optional performance indexes")

    # Optional external payload strategy for big/full-data graphs
    payloads: PayloadSpec | None = Field(default=None, description="Optional payload strategy for lazy-loading")
