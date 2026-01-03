"""Mermaid flowchart exporter for GraphSpec.

This module converts GraphSpec to Mermaid flowchart syntax, using subgraphs
to represent controller containment relationships.
"""

import hashlib
from collections import defaultdict

from pipelex.observability.graphspec.graphspec import (
    EdgeKind,
    EdgeSpec,
    GraphSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
)

# Valid Mermaid flowchart directions
VALID_DIRECTIONS = {"TB", "TD", "BT", "RL", "LR"}


def sanitize_mermaid_id(node_id: str) -> str:
    """Convert a node ID to a valid Mermaid identifier.

    Mermaid IDs cannot contain special characters like ':', '-', '.'.
    We use a hash-based approach to ensure uniqueness and validity.

    Args:
        node_id: The original node ID (may contain special characters).

    Returns:
        A sanitized Mermaid-safe identifier like 'n_abc1234567'.
    """
    # Using sha256 for hashing (only for ID generation, not security)
    hash_digest = hashlib.sha256(node_id.encode()).hexdigest()[:10]
    return f"n_{hash_digest}"


def escape_mermaid_label(label: str) -> str:
    """Escape special characters in Mermaid labels.

    Args:
        label: The label text to escape.

    Returns:
        Escaped label safe for use in Mermaid syntax.
    """
    # Escape quotes and other special characters
    return label.replace('"', "'").replace("[", "(").replace("]", ")")


def _get_node_label(node: NodeSpec) -> str:
    """Get the display label for a node.

    Args:
        node: The NodeSpec to get a label for.

    Returns:
        A human-readable label for the node.
    """
    if node.pipe_name:
        return escape_mermaid_label(node.pipe_name)
    if node.pipe_type:
        return escape_mermaid_label(node.pipe_type)
    return escape_mermaid_label(node.node_id)


def _build_containment_tree(
    edges: list[EdgeSpec],
) -> tuple[dict[str, list[str]], set[str]]:
    """Build a tree structure from CONTAINS edges.

    Args:
        edges: List of all edges.

    Returns:
        Tuple of:
        - dict mapping parent node_id to list of child node_ids
        - set of all node_ids that are children (have a parent)
    """
    children_map: dict[str, list[str]] = defaultdict(list)
    child_nodes: set[str] = set()

    for edge in edges:
        if edge.kind == EdgeKind.CONTAINS:
            children_map[edge.source].append(edge.target)
            child_nodes.add(edge.target)

    return dict(children_map), child_nodes


def _render_node(
    node: NodeSpec,
    mermaid_id: str,
    indent: str = "    ",
) -> str:
    """Render a single node in Mermaid syntax.

    Args:
        node: The NodeSpec to render.
        mermaid_id: The sanitized Mermaid ID for this node.
        indent: Indentation prefix.

    Returns:
        Mermaid node declaration string.
    """
    label = _get_node_label(node)

    # Choose shape based on node kind
    match node.kind:
        case NodeKind.INPUT | NodeKind.OUTPUT:
            # Pill/stadium shape for I/O
            node_str = f'{mermaid_id}(["{label}"])'
        case NodeKind.ARTIFACT:
            # Cylinder for artifacts
            node_str = f'{mermaid_id}[("{label}")]'
        case NodeKind.ERROR:
            # Rectangle with failed class
            node_str = f'{mermaid_id}["{label}"]:::failed'
        case NodeKind.CONTROLLER | NodeKind.PIPE_CALL | NodeKind.OPERATOR:
            # Rectangle for operators/pipes
            if node.status == NodeStatus.FAILED:
                node_str = f'{mermaid_id}["{label}"]:::failed'
            else:
                node_str = f'{mermaid_id}["{label}"]'

    return f"{indent}{node_str}"


def _render_subgraph_recursive(
    node_id: str,
    nodes_by_id: dict[str, NodeSpec],
    id_mapping: dict[str, str],
    children_map: dict[str, list[str]],
    edges: list[EdgeSpec],
    include_data_edges: bool,
    include_selected_outcome_edges: bool,
    indent_level: int = 1,
) -> list[str]:
    """Recursively render a node and its children as subgraphs.

    Args:
        node_id: The node to render.
        nodes_by_id: Map of node_id to NodeSpec.
        id_mapping: Map of node_id to sanitized Mermaid ID.
        children_map: Map of parent node_id to list of child node_ids.
        edges: All edges (for rendering non-contains edges).
        include_data_edges: Whether to include data edges.
        include_selected_outcome_edges: Whether to include selected outcome edges.
        indent_level: Current indentation level.

    Returns:
        List of Mermaid syntax lines.
    """
    lines: list[str] = []
    indent = "    " * indent_level
    node = nodes_by_id.get(node_id)
    mermaid_id = id_mapping.get(node_id, sanitize_mermaid_id(node_id))

    if node is None:
        return lines

    children = children_map.get(node_id, [])

    if children:
        # This is a controller with children - render as subgraph
        label = _get_node_label(node)
        subgraph_id = f"sg_{mermaid_id}"
        lines.append(f'{indent}subgraph {subgraph_id}["{label}"]')

        # Add a node inside the subgraph for the controller itself
        # This allows edges to connect to the controller
        inner_indent = "    " * (indent_level + 1)
        lines.append(f'{inner_indent}{mermaid_id}(("{label}"))')

        # Sort children for deterministic output
        sorted_children = sorted(
            children,
            key=lambda cid: (
                nodes_by_id.get(cid, NodeSpec(node_id=cid, kind=NodeKind.OPERATOR, status=NodeStatus.SCHEDULED)).kind,
                nodes_by_id.get(cid, NodeSpec(node_id=cid, kind=NodeKind.OPERATOR, status=NodeStatus.SCHEDULED)).pipe_name or "",
                cid,
            ),
        )

        for child_id in sorted_children:
            child_lines = _render_subgraph_recursive(
                node_id=child_id,
                nodes_by_id=nodes_by_id,
                id_mapping=id_mapping,
                children_map=children_map,
                edges=edges,
                include_data_edges=include_data_edges,
                include_selected_outcome_edges=include_selected_outcome_edges,
                indent_level=indent_level + 1,
            )
            lines.extend(child_lines)

        lines.append(f"{indent}end")
    else:
        # Leaf node - render as simple node
        lines.append(_render_node(node, mermaid_id, indent))

    return lines


def _render_edges(
    edges: list[EdgeSpec],
    id_mapping: dict[str, str],
    include_data_edges: bool,
    include_contains_edges: bool,
    include_selected_outcome_edges: bool,
) -> list[str]:
    """Render edges in Mermaid syntax.

    Args:
        edges: List of all edges.
        id_mapping: Map of node_id to sanitized Mermaid ID.
        include_data_edges: Whether to include DATA edges.
        include_contains_edges: Whether to include CONTAINS edges as arrows.
        include_selected_outcome_edges: Whether to include SELECTED_OUTCOME edges.

    Returns:
        List of Mermaid edge declaration lines.
    """
    lines: list[str] = []

    # Sort edges for deterministic output
    sorted_edges = sorted(edges, key=lambda edge: (edge.kind, edge.source, edge.target, edge.label or ""))

    for edge in sorted_edges:
        source_id = id_mapping.get(edge.source, sanitize_mermaid_id(edge.source))
        target_id = id_mapping.get(edge.target, sanitize_mermaid_id(edge.target))

        match edge.kind:
            case EdgeKind.CONTAINS:
                # CONTAINS edges can be rendered as arrows in addition to subgraph nesting
                if not include_contains_edges:
                    continue
                # Use dotted arrow with "contains" style for parent-child relationships
                lines.append(f"    {source_id} -.-> {target_id}")
            case EdgeKind.CONTROL:
                if edge.label:
                    lines.append(f'    {source_id} -->|"{escape_mermaid_label(edge.label)}"| {target_id}')
                else:
                    lines.append(f"    {source_id} --> {target_id}")
            case EdgeKind.DATA:
                if not include_data_edges:
                    continue
                if edge.label:
                    lines.append(f'    {source_id} -.->|"{escape_mermaid_label(edge.label)}"| {target_id}')
                else:
                    lines.append(f"    {source_id} -.-> {target_id}")
            case EdgeKind.SELECTED_OUTCOME:
                if not include_selected_outcome_edges:
                    continue
                if edge.label:
                    lines.append(f'    {source_id} -->|"{escape_mermaid_label(edge.label)}"| {target_id}')
                else:
                    lines.append(f"    {source_id} --> {target_id}")

    return lines


def graphspec_to_mermaid(
    graph: GraphSpec,
    *,
    direction: str = "TD",
    include_data_edges: bool = True,
    include_contains_edges: bool = False,
    include_selected_outcome_edges: bool = True,
) -> str:
    """Convert a GraphSpec to Mermaid flowchart syntax.

    Args:
        graph: The GraphSpec to convert.
        direction: Flowchart direction (TB, TD, BT, RL, LR). Defaults to "TD".
        include_data_edges: Whether to render DATA edges as dashed arrows.
        include_contains_edges: Whether to render CONTAINS as explicit arrows
            instead of subgraphs. Defaults to False (use subgraphs).
        include_selected_outcome_edges: Whether to render SELECTED_OUTCOME edges.

    Returns:
        Mermaid flowchart syntax as a string.

    Raises:
        ValueError: If direction is not a valid Mermaid direction.
    """
    if direction not in VALID_DIRECTIONS:
        msg = f"Invalid direction '{direction}'. Must be one of: {', '.join(sorted(VALID_DIRECTIONS))}"
        raise ValueError(msg)

    lines: list[str] = []

    # Header
    lines.append(f"flowchart {direction}")

    # Build ID mapping for all nodes
    id_mapping: dict[str, str] = {}
    for node in graph.nodes:
        id_mapping[node.node_id] = sanitize_mermaid_id(node.node_id)

    # Build node lookup
    nodes_by_id: dict[str, NodeSpec] = {node.node_id: node for node in graph.nodes}

    # Build containment tree
    children_map, child_nodes = _build_containment_tree(graph.edges)

    # Find root nodes (nodes that are not children of any other node)
    root_nodes = [node for node in graph.nodes if node.node_id not in child_nodes]

    # Sort root nodes for deterministic output
    sorted_roots = sorted(root_nodes, key=lambda node: (node.kind, node.pipe_name or "", node.node_id))

    # Render nodes (using subgraphs for containment)
    for root_node in sorted_roots:
        node_lines = _render_subgraph_recursive(
            node_id=root_node.node_id,
            nodes_by_id=nodes_by_id,
            id_mapping=id_mapping,
            children_map=children_map,
            edges=graph.edges,
            include_data_edges=include_data_edges,
            include_selected_outcome_edges=include_selected_outcome_edges,
        )
        lines.extend(node_lines)

    # Render edges
    edge_lines = _render_edges(
        edges=graph.edges,
        id_mapping=id_mapping,
        include_data_edges=include_data_edges,
        include_contains_edges=include_contains_edges,
        include_selected_outcome_edges=include_selected_outcome_edges,
    )
    if edge_lines:
        lines.append("")  # Blank line before edges
        lines.extend(edge_lines)

    # Style definitions
    lines.append("")
    lines.append("    %% Style definitions")
    lines.append("    classDef failed fill:#ffcccc,stroke:#cc0000")
    lines.append("    classDef controller fill:#e6f3ff,stroke:#0066cc")

    return "\n".join(lines)
