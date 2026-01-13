"""Transformer from GraphSpec + GraphAnalysis to ViewSpec for ReactFlow rendering.

This module provides the transformation logic to convert the canonical GraphSpec
and pre-computed GraphAnalysis into a ViewSpec that is optimized for ReactFlow
and other interactive graph viewers.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec import EdgeKind, GraphSpec, NodeKind, NodeStatus
from pipelex.graph.reactflow.viewspec import LayoutSpec, ViewEdge, ViewIndex, ViewNode, ViewSpec
from pipelex.tools.misc.package_utils import get_package_version


def _map_node_kind_to_view_type(kind: NodeKind) -> str:
    """Map GraphSpec NodeKind to ReactFlow ViewNode type.

    Args:
        kind: The NodeKind from GraphSpec.

    Returns:
        ReactFlow node type string.
    """
    match kind:
        case NodeKind.OPERATOR:
            return "operator"
        case NodeKind.CONTROLLER:
            return "controller"
        case NodeKind.INPUT:
            return "io"
        case NodeKind.OUTPUT:
            return "io"
        case NodeKind.ARTIFACT:
            return "artifact"
        case NodeKind.ERROR:
            return "error"
        case NodeKind.PIPE_CALL:
            return "operator"  # Treat pipe_call as operator for now


def _map_edge_kind_to_view_type(kind: EdgeKind) -> str:
    """Map GraphSpec EdgeKind to ReactFlow ViewEdge type.

    Args:
        kind: The EdgeKind from GraphSpec.

    Returns:
        ReactFlow edge type string.
    """
    match kind:
        case EdgeKind.DATA:
            return "data"
        case EdgeKind.CONTROL:
            return "control"
        case EdgeKind.CONTAINS:
            return "contains"
        case EdgeKind.SELECTED_OUTCOME:
            return "control"  # Treat selected_outcome as control for now


def _build_node_label(node_spec: Any) -> str:
    """Build a display label for a node.

    Args:
        node_spec: The NodeSpec to build a label for.

    Returns:
        Display label string.
    """
    if node_spec.pipe_code:
        return str(node_spec.pipe_code)
    if node_spec.pipe_type:
        return str(node_spec.pipe_type)
    return str(node_spec.node_id)


def _build_ui_classes(status: NodeStatus) -> list[str]:
    """Build UI classes based on node status.

    Args:
        status: The NodeStatus.

    Returns:
        List of CSS class names.
    """
    match status:
        case NodeStatus.SUCCEEDED:
            return ["ok", "succeeded"]
        case NodeStatus.FAILED:
            return ["failed", "error"]
        case NodeStatus.RUNNING:
            return ["running", "active"]
        case NodeStatus.SCHEDULED:
            return ["scheduled", "pending"]
        case NodeStatus.SKIPPED:
            return ["skipped"]
        case NodeStatus.CANCELED:
            return ["canceled"]


def _build_ui_badges(timing: Any | None, metrics: dict[str, float] | None) -> list[str]:
    """Build UI badges from timing and metrics.

    Args:
        timing: Optional TimingSpec.
        metrics: Optional metrics dict.

    Returns:
        List of badge strings.
    """
    badges: list[str] = []
    if timing:
        badges.append(f"{timing.duration:.2f}s")
    if metrics:
        for key, value in metrics.items():
            if key == "llm_tokens":
                badges.append(f"{int(value)} tokens")
            elif key == "cost_usd":
                badges.append(f"${value:.4f}")
    return badges


def _build_io_preview(node_io: Any) -> dict[str, Any]:
    """Build I/O preview for inspector from NodeIOSpec.

    Args:
        node_io: The NodeIOSpec to extract previews from.

    Returns:
        Dict with input and output previews.
    """
    io_preview: dict[str, Any] = {}
    if node_io.inputs:
        io_preview["inputs"] = [
            {
                "name": io.name,
                "concept": io.concept,
                "preview": io.preview,
                "size": io.size,
                "digest": io.digest,
            }
            for io in node_io.inputs
        ]
    if node_io.outputs:
        io_preview["outputs"] = [
            {
                "name": io.name,
                "concept": io.concept,
                "preview": io.preview,
                "size": io.size,
                "digest": io.digest,
            }
            for io in node_io.outputs
        ]
    return io_preview


def _build_inspector_data(node_spec: Any) -> dict[str, Any]:
    """Build inspector data for a node.

    Args:
        node_spec: The NodeSpec to build inspector data for.

    Returns:
        Inspector data dict.
    """
    inspector: dict[str, Any] = {}
    if node_spec.pipe_code:
        inspector["pipe_code"] = node_spec.pipe_code
    if node_spec.pipe_type:
        inspector["pipe_type"] = node_spec.pipe_type
    if node_spec.timing:
        inspector["timing"] = {
            "started_at": node_spec.timing.started_at.isoformat(),
            "ended_at": node_spec.timing.ended_at.isoformat(),
        }
    if node_spec.node_io:
        inspector["io_preview"] = _build_io_preview(node_spec.node_io)
    if node_spec.error:
        inspector["error"] = {
            "error_type": node_spec.error.error_type,
            "message": node_spec.error.message,
            "stack": node_spec.error.stack,
        }
    if node_spec.tags:
        inspector["tags"] = node_spec.tags
    if node_spec.metrics:
        inspector["metrics"] = node_spec.metrics
    return inspector


def graphspec_to_viewspec(
    graph: GraphSpec,
    analysis: GraphAnalysis,
    *,
    options: dict[str, Any] | None = None,
    layout: LayoutSpec | None = None,
) -> ViewSpec:
    """Transform GraphSpec + GraphAnalysis into ViewSpec for ReactFlow.

    Args:
        graph: The canonical GraphSpec.
        analysis: Pre-computed GraphAnalysis.
        options: Optional view options (show_data_edges, collapse_controllers, redaction, etc.).
        layout: Optional layout configuration. If None, uses default LayoutSpec.

    Returns:
        ViewSpec ready for ReactFlow rendering.
    """
    if options is None:
        options = {}
    if layout is None:
        layout = LayoutSpec()

    # Build ViewNodes
    view_nodes: list[ViewNode] = []
    for node_spec in graph.nodes:
        # Determine parent_id from containment tree
        parent_id: str | None = None
        for parent_node_id, children in analysis.containment_tree.items():
            if node_spec.node_id in children:
                parent_id = parent_node_id
                break

        # Build UI classes and badges
        ui_classes = _build_ui_classes(node_spec.status)
        ui_badges = _build_ui_badges(node_spec.timing, node_spec.metrics)
        ui_data: dict[str, Any] = {"classes": ui_classes}
        if ui_badges:
            ui_data["badges"] = ui_badges

        # Build inspector data
        inspector_data = _build_inspector_data(node_spec)

        view_node = ViewNode(
            id=node_spec.node_id,
            label=_build_node_label(node_spec),
            kind=node_spec.kind,
            status=node_spec.status,
            type=_map_node_kind_to_view_type(node_spec.kind),
            parent_id=parent_id,
            extent="parent" if parent_id else None,
            ui=ui_data,
            inspector=inspector_data,
        )
        view_nodes.append(view_node)

    # Build ViewEdges
    view_edges: list[ViewEdge] = []
    show_data_edges = options.get("show_data_edges", True)
    collapse_controllers = options.get("collapse_controllers", False)

    for edge_spec in graph.edges:
        # Skip CONTAINS edges if we're using parent_id for containment
        if edge_spec.kind == EdgeKind.CONTAINS:
            continue

        # Skip DATA edges if show_data_edges is False
        if edge_spec.kind == EdgeKind.DATA and not show_data_edges:
            continue

        # Skip edges to/from controllers if collapsing
        if collapse_controllers:
            source_node = analysis.nodes_by_id.get(edge_spec.source)
            target_node = analysis.nodes_by_id.get(edge_spec.target)
            if (source_node and analysis.is_controller(source_node.node_id)) or (target_node and analysis.is_controller(target_node.node_id)):
                continue

        view_edge = ViewEdge(
            id=edge_spec.edge_id,
            source=edge_spec.source,
            target=edge_spec.target,
            kind=edge_spec.kind,
            label=edge_spec.label,
            type=_map_edge_kind_to_view_type(edge_spec.kind),
            animated=edge_spec.kind == EdgeKind.DATA,
            hidden=False,
        )
        view_edges.append(view_edge)

    # Build ViewIndex (optional but recommended for performance)
    edges_by_node: dict[str, list[str]] = defaultdict(list)
    for edge_spec in graph.edges:
        edges_by_node[edge_spec.source].append(edge_spec.edge_id)
        edges_by_node[edge_spec.target].append(edge_spec.edge_id)

    search_index: dict[str, list[str]] = defaultdict(list)
    for node_spec in graph.nodes:
        if node_spec.pipe_code:
            search_index[f"pipe_code:{node_spec.pipe_code}"].append(node_spec.node_id)
        if node_spec.pipe_type:
            search_index[f"pipe_type:{node_spec.pipe_type}"].append(node_spec.node_id)
        if node_spec.status:
            search_index[f"status:{node_spec.status}"].append(node_spec.node_id)

    view_index = ViewIndex(
        edges_by_node=dict(edges_by_node),
        children_by_parent=analysis.containment_tree,
        search=dict(search_index),
    )

    # Build source metadata
    source_metadata: dict[str, Any] = {
        "producer": f"pipelex {get_package_version()}",
    }
    if graph.pipeline_ref.domain:
        source_metadata["domain"] = graph.pipeline_ref.domain
    if graph.pipeline_ref.main_pipe:
        source_metadata["main_pipe"] = graph.pipeline_ref.main_pipe

    # Create ViewSpec
    return ViewSpec(
        created_at=datetime.now(timezone.utc),
        graph_id=graph.graph_id,
        source=source_metadata,
        engine="reactflow",
        options=options,
        layout=layout,
        nodes=view_nodes,
        edges=view_edges,
        index=view_index,
    )
