"""Mermaidflow factory for creating Mermaid flowcharts from GraphSpec.

This module converts GraphSpec to Mermaid flowchart syntax (from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory view),
using subgraphs to represent controller containment relationships.

The factory uses GraphAnalysis for pre-computed graph analysis, avoiding
duplicated analysis logic across different rendering functions.
"""

import operator
from typing import Any

from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graph_config import GraphConfig
from pipelex.graph.graphspec import (
    GraphSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
)
from pipelex.graph.mermaidflow.mermaidflow import Mermaidflow
from pipelex.graph.mermaidflow.mermaidflow_utils import make_stuff_id
from pipelex.graph.mermaidflow.stuff_collector import (
    collect_stuff_content_type,
    collect_stuff_data,
    collect_stuff_data_html,
    collect_stuff_data_text,
    collect_stuff_metadata,
)
from pipelex.tools.mermaid.mermaid_utils import escape_mermaid_label, sanitize_mermaid_id
from pipelex.tools.misc.chart_utils import FlowchartDirection

# Light pastel colors for subgraph depth coloring (cycles through these)
SUBGRAPH_DEPTH_COLORS = [
    "#e6f3ff",  # Light blue
    "#e6ffe6",  # Light green
    "#fffde6",  # Light yellow
    "#ffe6f0",  # Light pink
    "#f0e6ff",  # Light purple
    "#fff3e6",  # Light orange
]


class MermaidflowFactory:
    """Factory for creating Mermaid flowcharts from GraphSpec.

    This factory provides classmethods for converting GraphSpec to Mermaid syntax,
    showing data flow with orchestration grouping through subgraphs.
    """

    @classmethod
    def make_from_graphspec(
        cls,
        graph: GraphSpec,
        graph_config: GraphConfig,
        *,
        direction: FlowchartDirection | None = None,
        show_stuff_codes: bool = False,
        include_subgraphs: bool = True,
    ) -> Mermaidflow:
        """Convert a GraphSpec to a from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory Mermaid flowchart.

        This view combines data flow visualization with orchestration grouping:
        - Data flow visualization: Shows Stuff nodes (data items) flowing between pipes
        - Orchestration grouping: PipeControllers rendered as subgraphs containing their children

        When include_subgraphs is True (default):
        - Controller nodes as subgraphs containing their child pipes
        - Pipe nodes as rectangles inside their controller subgraphs
        - Stuff nodes as pills (stadium shape) inside subgraphs next to their producer pipe
        - Stuff nodes without a producer (pipeline inputs) at top level

        When include_subgraphs is False:
        - All pipe nodes rendered flat (no hierarchy)
        - All stuff nodes rendered flat at top level
        - Only pipes participating in data flow are shown

        Edges from producer pipes to stuff, and from stuff to consumer pipes are always shown.

        Args:
            graph: The GraphSpec to convert.
            graph_config: Configuration controlling data inclusion and rendering options.
            direction: Flowchart direction. Defaults to TOP_DOWN if not specified.
            show_stuff_codes: Whether to show stuff_code (digest) in stuff labels.
            include_subgraphs: Whether to render controller hierarchy as subgraphs.

        Returns:
            Mermaidflow containing mermaid code and optional stuff data mapping.
        """
        effective_direction = direction or FlowchartDirection.TOP_DOWN
        lines: list[str] = []

        # Pre-compute graph analysis
        analysis = GraphAnalysis.from_graphspec(graph)

        # Header
        lines.append(f"flowchart {effective_direction.mermaid_code}")

        # Build ID mapping for all nodes
        id_mapping: dict[str, str] = {}
        for node in graph.nodes:
            id_mapping[node.node_id] = sanitize_mermaid_id(node.node_id)

        # Build stuff registry as tuple format for compatibility with rendering code
        stuff_registry: dict[str, tuple[str, str | None]] = {}
        for digest, stuff_info in analysis.stuff_registry.items():
            stuff_registry[digest] = (stuff_info.name, stuff_info.concept)

        # Will be populated during rendering
        stuff_id_mapping: dict[str, str] = {}

        # Track subgraph depths for coloring (only used when include_subgraphs=True)
        subgraph_depths: dict[str, int] = {}

        # Skip if no data flow information
        if not analysis.has_data_flow_info():
            lines.append("")
            lines.append("    %% No data flow information available")
            lines.append("    note[No IOSpec data captured. Run with data flow tracing enabled.]")
            mermaid_code = "\n".join(lines)
            return Mermaidflow(mermaid_code=mermaid_code, stuff_data=None)

        if include_subgraphs:
            # Render pipe nodes and their produced stuff within controller subgraphs
            lines.append("")
            lines.append("    %% Pipe and stuff nodes within controller subgraphs")
            for root_node in analysis.root_nodes:
                node_lines = cls._render_subgraph_recursive(
                    node_id=root_node.node_id,
                    nodes_by_id=analysis.nodes_by_id,
                    id_mapping=id_mapping,
                    children_map=analysis.containment_tree,
                    stuff_registry=stuff_registry,
                    stuff_producers=analysis.stuff_producers,
                    stuff_id_mapping=stuff_id_mapping,
                    subgraph_depths=subgraph_depths,
                    show_stuff_codes=show_stuff_codes,
                )
                lines.extend(node_lines)

            # Render stuff nodes without a producer (pipeline inputs) at top level
            orphan_stuffs = [(digest, name, concept) for digest, (name, concept) in stuff_registry.items() if digest not in analysis.stuff_producers]
            if orphan_stuffs:
                lines.append("")
                lines.append("    %% Pipeline input stuff nodes (no producer)")
                for digest, name, concept in sorted(orphan_stuffs, key=operator.itemgetter(1)):
                    stuff_line = cls._render_stuff_node(
                        digest=digest,
                        name=name,
                        concept=concept,
                        stuff_id_mapping=stuff_id_mapping,
                        show_stuff_codes=show_stuff_codes,
                        indent="    ",
                    )
                    lines.append(stuff_line)
        else:
            # Flat rendering: no subgraphs, only pipes participating in data flow
            lines.append("")
            lines.append("    %% Pipe nodes (flat view)")

            # Only render pipes that participate in data flow
            participating_pipes: set[str] = set(analysis.stuff_producers.values())
            for consumers in analysis.stuff_consumers.values():
                participating_pipes.update(consumers)

            for node in sorted(graph.nodes, key=lambda n_iter: (n_iter.pipe_code or "", n_iter.node_id)):
                if node.node_id not in participating_pipes:
                    continue

                mermaid_id = id_mapping[node.node_id]
                label = cls._get_node_label(node)
                if node.status == NodeStatus.FAILED:
                    lines.append(f'    {mermaid_id}["{label}"]:::pipe_failed')
                else:
                    lines.append(f'    {mermaid_id}["{label}"]:::pipe')

            # Render all stuff nodes flat at top level
            lines.append("")
            lines.append("    %% Stuff nodes (data items)")
            for digest, (name, concept) in sorted(stuff_registry.items(), key=lambda item: item[1][0]):
                stuff_line = cls._render_stuff_node(
                    digest=digest,
                    name=name,
                    concept=concept,
                    stuff_id_mapping=stuff_id_mapping,
                    show_stuff_codes=show_stuff_codes,
                    indent="    ",
                )
                lines.append(stuff_line)

        # Render edges: producer -> stuff
        lines.append("")
        lines.append("    %% Data flow edges: producer -> stuff -> consumer")

        for digest, producer_node_id in sorted(analysis.stuff_producers.items(), key=operator.itemgetter(0)):
            producer_mermaid_id = id_mapping.get(producer_node_id)
            prod_stuff_mermaid_id = stuff_id_mapping.get(digest)
            if producer_mermaid_id and prod_stuff_mermaid_id:
                lines.append(f"    {producer_mermaid_id} --> {prod_stuff_mermaid_id}")

        # Render edges: stuff -> consumer
        for digest, consumer_node_ids in sorted(analysis.stuff_consumers.items(), key=operator.itemgetter(0)):
            cons_stuff_mermaid_id = stuff_id_mapping.get(digest)
            if not cons_stuff_mermaid_id:
                continue
            for consumer_node_id in sorted(consumer_node_ids):
                consumer_mermaid_id = id_mapping.get(consumer_node_id)
                if consumer_mermaid_id:
                    lines.append(f"    {cons_stuff_mermaid_id} --> {consumer_mermaid_id}")

        # Style definitions
        lines.append("")
        lines.append("    %% Style definitions")
        lines.append("    classDef failed fill:#ffcccc,stroke:#cc0000")
        lines.append("    classDef stuff fill:#fff3e6,stroke:#cc6600,stroke-width:2px")
        if include_subgraphs:
            lines.append("    classDef controller fill:#e6f3ff,stroke:#0066cc")
            # Apply depth-based colors to subgraphs
            if subgraph_depths:
                lines.append("")
                lines.append("    %% Subgraph depth-based coloring")
                for subgraph_id, sg_depth in sorted(subgraph_depths.items()):
                    color = SUBGRAPH_DEPTH_COLORS[sg_depth % len(SUBGRAPH_DEPTH_COLORS)]
                    lines.append(f"    style {subgraph_id} fill:{color}")
        else:
            lines.append("    classDef pipe fill:#e6f3ff,stroke:#0066cc")
            lines.append("    classDef pipe_failed fill:#ffcccc,stroke:#cc0000")

        mermaid_code = "\n".join(lines)

        # Collect stuff data in configured formats
        stuff_data: dict[str, Any] | None = None
        stuff_data_text: dict[str, str] | None = None
        stuff_data_html: dict[str, str] | None = None

        if graph_config.data_inclusion.stuff_json_content:
            stuff_data = collect_stuff_data(graph=graph)
        if graph_config.data_inclusion.stuff_text_content:
            stuff_data_text = collect_stuff_data_text(graph=graph)
        if graph_config.data_inclusion.stuff_html_content:
            stuff_data_html = collect_stuff_data_html(graph=graph)

        # Collect metadata and content_type if any stuff data is present
        stuff_metadata: dict[str, dict[str, str]] | None = None
        stuff_content_type: dict[str, str] | None = None
        if stuff_data or stuff_data_text or stuff_data_html:
            stuff_metadata = collect_stuff_metadata(graph=graph)
            stuff_content_type = collect_stuff_content_type(graph=graph)

        return Mermaidflow(
            mermaid_code=mermaid_code,
            stuff_data=stuff_data,
            stuff_data_text=stuff_data_text,
            stuff_data_html=stuff_data_html,
            stuff_metadata=stuff_metadata,
            stuff_content_type=stuff_content_type,
        )

    @classmethod
    def _get_node_label(cls, node: NodeSpec) -> str:
        """Get the display label for a node.

        Args:
            node: The NodeSpec to get a label for.

        Returns:
            A human-readable label for the node.
        """
        if node.pipe_code:
            return escape_mermaid_label(node.pipe_code)
        if node.pipe_type:
            return escape_mermaid_label(node.pipe_type)
        return escape_mermaid_label(node.node_id)

    @classmethod
    def _render_node(
        cls,
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
        label = cls._get_node_label(node)

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

    @classmethod
    def _render_stuff_node(
        cls,
        digest: str,
        name: str,
        concept: str | None,
        stuff_id_mapping: dict[str, str],
        show_stuff_codes: bool,
        indent: str = "    ",
    ) -> str:
        """Render a single stuff node in Mermaid syntax.

        Args:
            digest: The stuff digest (unique identifier).
            name: The stuff name.
            concept: The stuff concept (optional).
            stuff_id_mapping: Map to store/retrieve stuff mermaid IDs.
            show_stuff_codes: Whether to show digest in label.
            indent: Indentation prefix.

        Returns:
            Mermaid stuff node declaration string.
        """
        stuff_mermaid_id = make_stuff_id(digest)
        stuff_id_mapping[digest] = stuff_mermaid_id

        # Build label
        if show_stuff_codes:
            label = f"{escape_mermaid_label(name)} ({digest[:5]})"
        else:
            label = escape_mermaid_label(name)

        if concept:
            label = f"{label}<br/>{escape_mermaid_label(concept)}"

        return f'{indent}{stuff_mermaid_id}(["{label}"]):::stuff'

    @classmethod
    def _render_subgraph_recursive(
        cls,
        node_id: str,
        nodes_by_id: dict[str, NodeSpec],
        id_mapping: dict[str, str],
        children_map: dict[str, list[str]],
        stuff_registry: dict[str, tuple[str, str | None]],
        stuff_producers: dict[str, str],
        stuff_id_mapping: dict[str, str],
        subgraph_depths: dict[str, int],
        show_stuff_codes: bool,
        indent_level: int = 1,
        depth: int = 0,
    ) -> list[str]:
        """Recursively render pipes and their produced stuff within controller subgraphs.

        This renders both pipe nodes and their produced stuff nodes inside subgraphs.

        Args:
            node_id: The node to render.
            nodes_by_id: Map of node_id to NodeSpec.
            id_mapping: Map of node_id to sanitized Mermaid ID.
            children_map: Map of parent node_id to list of child node_ids.
            stuff_registry: Map of digest to (name, concept) for all stuffs.
            stuff_producers: Map of digest to producer node_id.
            stuff_id_mapping: Map to store stuff mermaid IDs (mutated).
            subgraph_depths: Map to track subgraph IDs and their depths (mutated).
            show_stuff_codes: Whether to show digest in stuff labels.
            indent_level: Current indentation level.
            depth: Current depth in the subgraph hierarchy (for coloring).

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
            label = cls._get_node_label(node)
            subgraph_id = f"sg_{mermaid_id}"
            lines.append(f'{indent}subgraph {subgraph_id}["{label}"]')

            # Track this subgraph's depth for styling
            subgraph_depths[subgraph_id] = depth

            # Sort children for deterministic output
            sorted_children = sorted(
                children,
                key=lambda cid: (
                    nodes_by_id.get(cid, NodeSpec(node_id=cid, kind=NodeKind.OPERATOR, status=NodeStatus.SCHEDULED)).kind,
                    nodes_by_id.get(cid, NodeSpec(node_id=cid, kind=NodeKind.OPERATOR, status=NodeStatus.SCHEDULED)).pipe_code or "",
                    cid,
                ),
            )

            for child_id in sorted_children:
                child_lines = cls._render_subgraph_recursive(
                    node_id=child_id,
                    nodes_by_id=nodes_by_id,
                    id_mapping=id_mapping,
                    children_map=children_map,
                    stuff_registry=stuff_registry,
                    stuff_producers=stuff_producers,
                    stuff_id_mapping=stuff_id_mapping,
                    subgraph_depths=subgraph_depths,
                    show_stuff_codes=show_stuff_codes,
                    indent_level=indent_level + 1,
                    depth=depth + 1,
                )
                lines.extend(child_lines)

            lines.append(f"{indent}end")
        else:
            # Leaf node - render as simple node
            lines.append(cls._render_node(node, mermaid_id, indent))

            # Also render any stuff nodes produced by this pipe
            for digest, producer_node_id in stuff_producers.items():
                if producer_node_id == node_id and digest in stuff_registry:
                    name, concept = stuff_registry[digest]
                    stuff_line = cls._render_stuff_node(
                        digest=digest,
                        name=name,
                        concept=concept,
                        stuff_id_mapping=stuff_id_mapping,
                        show_stuff_codes=show_stuff_codes,
                        indent=indent,
                    )
                    lines.append(stuff_line)

        return lines
