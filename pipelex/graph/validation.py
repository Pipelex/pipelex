"""GraphSpec validation functions.

This module provides validation functions to enforce GraphSpec invariants.
"""

from pipelex.graph.exceptions import GraphSpecValidationError
from pipelex.graph.graphspec import GraphSpec, NodeStatus


def validate_graphspec(graph: GraphSpec) -> None:
    """Validate a GraphSpec instance against all invariants.

    Args:
        graph: The GraphSpec instance to validate.

    Raises:
        GraphSpecValidationError: If any invariant is violated.

    Invariants checked:
        - All edge sources must reference existing node IDs
        - All edge targets must reference existing node IDs
        - Node IDs must be unique
        - Edge IDs must be unique
        - Nodes with status=failed must have an error specification
    """
    _validate_unique_node_ids(graph)
    _validate_unique_edge_ids(graph)
    _validate_edge_references(graph)
    _validate_failed_nodes_have_errors(graph)


def _validate_unique_node_ids(graph: GraphSpec) -> None:
    """Validate that all node IDs are unique."""
    seen_ids: set[str] = set()
    for node in graph.nodes:
        if node.node_id in seen_ids:
            msg = f"Duplicate node ID found: '{node.node_id}'"
            raise GraphSpecValidationError(msg)
        seen_ids.add(node.node_id)


def _validate_unique_edge_ids(graph: GraphSpec) -> None:
    """Validate that all edge IDs are unique."""
    seen_ids: set[str] = set()
    for edge in graph.edges:
        if edge.edge_id in seen_ids:
            msg = f"Duplicate edge ID found: '{edge.edge_id}'"
            raise GraphSpecValidationError(msg)
        seen_ids.add(edge.edge_id)


def _validate_edge_references(graph: GraphSpec) -> None:
    """Validate that all edge source/target references exist in nodes."""
    node_ids = {node.node_id for node in graph.nodes}

    for edge in graph.edges:
        if edge.source not in node_ids:
            msg = f"Edge '{edge.edge_id}' references non-existent source node: '{edge.source}'"
            raise GraphSpecValidationError(msg)
        if edge.target not in node_ids:
            msg = f"Edge '{edge.edge_id}' references non-existent target node: '{edge.target}'"
            raise GraphSpecValidationError(msg)


def _validate_failed_nodes_have_errors(graph: GraphSpec) -> None:
    """Validate that nodes with failed status have error specifications."""
    for node in graph.nodes:
        if node.status == NodeStatus.FAILED and node.error is None:
            msg = f"Node '{node.node_id}' has status=failed but no error specification"
            raise GraphSpecValidationError(msg)
