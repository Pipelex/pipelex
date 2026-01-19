"""GraphAnalysis - Pre-computed analysis of a GraphSpec for rendering.

This module provides a shared analysis layer that extracts and computes
common information needed by multiple graph renderers (Mermaid, ReactFlow, etc.).

The GraphAnalysis model is derived from GraphSpec and can be regenerated at any time.
It provides efficient lookups and pre-computed relationships without modifying the
canonical GraphSpec.
"""

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipelex.graph.graphspec import EdgeKind, GraphSpec, NodeSpec
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class StuffInfo(BaseModel):
    """Information about a stuff (data item) for rendering.

    Represents a piece of data that flows between pipes in the execution graph.
    The digest serves as a unique identifier for the stuff.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    concept: str | None = None
    data: str | dict[str, Any] | list[str] | list[dict[str, Any]] | None = None


class GraphAnalysis(BaseModel):
    """Pre-computed analysis of a GraphSpec for rendering.

    This model extracts and organizes information from a GraphSpec that is
    commonly needed by graph renderers. It provides:

    - Node lookups and categorization
    - Containment hierarchy (parent/child relationships)
    - Data flow tracking (stuff producers and consumers)
    - Root node identification

    The analysis is deterministic: the same GraphSpec will always produce
    the same GraphAnalysis.
    """

    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)

    # Core lookups
    nodes_by_id: dict[str, NodeSpec] = Field(default_factory=dict, description="Map of node_id to NodeSpec for fast lookup")

    # Containment hierarchy
    containment_tree: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of parent node_id to list of child node_ids (from CONTAINS edges)",
    )
    child_node_ids: set[str] = Field(
        default_factory=set,
        description="Set of all node_ids that are children (targets of CONTAINS edges)",
    )
    controller_node_ids: set[str] = Field(
        default_factory=set,
        description="Set of node_ids that are controllers (have children in containment_tree)",
    )
    root_nodes: list[NodeSpec] = Field(
        default_factory=empty_list_factory_of(NodeSpec),
        description="Nodes that are not children of any other node (top-level nodes)",
    )

    # Data flow tracking
    stuff_registry: dict[str, StuffInfo] = Field(
        default_factory=dict,
        description="Map of digest to StuffInfo for all stuffs in the graph",
    )
    stuff_producers: dict[str, str] = Field(
        default_factory=dict,
        description="Map of digest to producer node_id",
    )
    stuff_consumers: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of digest to list of consumer node_ids",
    )

    @classmethod
    def from_graphspec(cls, graph: GraphSpec) -> "GraphAnalysis":
        """Build a GraphAnalysis from a GraphSpec.

        This method extracts all the information needed for rendering from the
        GraphSpec and organizes it for efficient access.

        Args:
            graph: The GraphSpec to analyze.

        Returns:
            A GraphAnalysis containing pre-computed lookups and relationships.
        """
        # Build node lookup
        nodes_by_id: dict[str, NodeSpec] = {node.node_id: node for node in graph.nodes}

        # Build containment tree from CONTAINS edges
        containment_tree: dict[str, list[str]] = defaultdict(list)
        child_node_ids: set[str] = set()

        for edge in graph.edges:
            if edge.kind == EdgeKind.CONTAINS:
                containment_tree[edge.source].append(edge.target)
                child_node_ids.add(edge.target)

        # Convert defaultdict to regular dict for Pydantic
        containment_tree = dict(containment_tree)

        # Controller IDs are nodes that have children
        controller_node_ids: set[str] = set(containment_tree.keys())

        # Root nodes are nodes that are not children of any other node
        root_nodes: list[NodeSpec] = [node for node in graph.nodes if node.node_id not in child_node_ids]

        # Sort root nodes for deterministic output
        root_nodes = sorted(root_nodes, key=lambda node: (node.kind, node.pipe_code or "", node.node_id))

        # Build stuff registry and producer/consumer maps
        stuff_registry: dict[str, StuffInfo] = {}
        stuff_producers: dict[str, str] = {}
        stuff_consumers: dict[str, list[str]] = defaultdict(list)

        for node in graph.nodes:
            # Skip controllers - they don't directly transform data
            if node.node_id in controller_node_ids:
                continue

            # Collect outputs (this node produces these stuffs)
            for output_spec in node.node_io.outputs:
                if output_spec.digest:
                    stuff_registry[output_spec.digest] = StuffInfo(
                        name=output_spec.name,
                        concept=output_spec.concept,
                        data=output_spec.data,
                    )
                    stuff_producers[output_spec.digest] = node.node_id

            # Collect inputs (this node consumes these stuffs)
            for input_spec in node.node_io.inputs:
                if input_spec.digest:
                    # Register stuff even if we don't know the producer (pipeline input)
                    if input_spec.digest not in stuff_registry:
                        stuff_registry[input_spec.digest] = StuffInfo(
                            name=input_spec.name,
                            concept=input_spec.concept,
                            data=input_spec.data,
                        )
                    stuff_consumers[input_spec.digest].append(node.node_id)

        # Convert defaultdict to regular dict for Pydantic
        stuff_consumers = dict(stuff_consumers)

        return cls(
            nodes_by_id=nodes_by_id,
            containment_tree=containment_tree,
            child_node_ids=child_node_ids,
            controller_node_ids=controller_node_ids,
            root_nodes=root_nodes,
            stuff_registry=stuff_registry,
            stuff_producers=stuff_producers,
            stuff_consumers=stuff_consumers,
        )

    def get_children(self, node_id: str) -> list[str]:
        """Get the child node IDs for a given parent node.

        Args:
            node_id: The parent node ID.

        Returns:
            List of child node IDs, or empty list if no children.
        """
        return self.containment_tree.get(node_id, [])

    def is_controller(self, node_id: str) -> bool:
        """Check if a node is a controller (has children).

        Args:
            node_id: The node ID to check.

        Returns:
            True if the node has children in the containment tree.
        """
        return node_id in self.controller_node_ids

    def is_root(self, node_id: str) -> bool:
        """Check if a node is a root node (not a child of any other node).

        Args:
            node_id: The node ID to check.

        Returns:
            True if the node is not a child of any other node.
        """
        return node_id not in self.child_node_ids

    def get_stuff_info(self, digest: str) -> StuffInfo | None:
        """Get information about a stuff by its digest.

        Args:
            digest: The stuff digest (unique identifier).

        Returns:
            StuffInfo if found, None otherwise.
        """
        return self.stuff_registry.get(digest)

    def get_producer(self, digest: str) -> str | None:
        """Get the producer node ID for a stuff.

        Args:
            digest: The stuff digest.

        Returns:
            Producer node ID if found, None otherwise.
        """
        return self.stuff_producers.get(digest)

    def get_consumers(self, digest: str) -> list[str]:
        """Get the consumer node IDs for a stuff.

        Args:
            digest: The stuff digest.

        Returns:
            List of consumer node IDs, or empty list if no consumers.
        """
        return self.stuff_consumers.get(digest, [])

    def has_data_flow_info(self) -> bool:
        """Check if the graph has any data flow information.

        Returns:
            True if there are any stuffs registered.
        """
        return len(self.stuff_registry) > 0
