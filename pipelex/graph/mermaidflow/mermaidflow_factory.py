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
    EdgeSpec,
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
            # Track which orphan stuffs have been rendered inside subgraphs
            # This allows batch item stuffs to be placed inside their consumer's subgraph
            rendered_orphan_stuffs: set[str] = set()

            # Build mapping of controller node_id → {digest: (name, concept)} for parallel_combine
            # target stuffs. These are outputs of parallel controllers and should be rendered
            # inside the controller's subgraph rather than as orphans at top level.
            # We collect the stuff info from controller node outputs directly, because these
            # stuffs may not be in stuff_registry (which skips controller nodes).
            controller_output_stuffs: dict[str, dict[str, tuple[str, str | None]]] = {}
            for edge in graph.edges:
                if edge.kind.is_parallel_combine and edge.target_stuff_digest:
                    controller_output_stuffs.setdefault(edge.target, {})[edge.target_stuff_digest] = ("", None)
            # Resolve names and concepts from the controller nodes' outputs
            for controller_id, digest_map in controller_output_stuffs.items():
                controller_node = analysis.nodes_by_id.get(controller_id)
                if controller_node:
                    for output_spec in controller_node.node_io.outputs:
                        if output_spec.digest and output_spec.digest in digest_map:
                            digest_map[output_spec.digest] = (output_spec.name, output_spec.concept)

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
                    stuff_consumers=analysis.stuff_consumers,
                    stuff_id_mapping=stuff_id_mapping,
                    subgraph_depths=subgraph_depths,
                    show_stuff_codes=show_stuff_codes,
                    rendered_orphan_stuffs=rendered_orphan_stuffs,
                    controller_output_stuffs=controller_output_stuffs,
                )
                lines.extend(node_lines)

            # Render stuff nodes without a producer (pipeline inputs) at top level
            # Skip any that were already rendered inside subgraphs (e.g., batch item stuffs)
            orphan_stuffs = [
                (digest, name, concept)
                for digest, (name, concept) in stuff_registry.items()
                if digest not in analysis.stuff_producers and digest not in rendered_orphan_stuffs
            ]
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

        # Build supplementary stuff info from all nodes (including controllers)
        # This is needed for batch_aggregate target_stuff_digest which may not be in stuff_registry
        # (GraphAnalysis.stuff_registry skips controller outputs)
        all_stuff_info: dict[str, tuple[str, str | None]] = {}
        for node in graph.nodes:
            for output_spec in node.node_io.outputs:
                if output_spec.digest and output_spec.digest not in all_stuff_info:
                    all_stuff_info[output_spec.digest] = (output_spec.name, output_spec.concept)

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

        # Render batch edges (BATCH_ITEM and BATCH_AGGREGATE) with dashed styling
        # These edges connect stuff-to-stuff (not node-to-node) because their source/target
        # are controllers rendered as Mermaid subgraphs, not nodes.
        batch_item_edges = [edge for edge in graph.edges if edge.kind.is_batch_item]
        batch_aggregate_edges = [edge for edge in graph.edges if edge.kind.is_batch_aggregate]

        if batch_item_edges or batch_aggregate_edges:
            lines.append("")
            lines.append("    %% Batch edges: list-item relationships")
            cls._render_dashed_edges(batch_item_edges, lines, stuff_id_mapping, all_stuff_info, show_stuff_codes)
            cls._render_dashed_edges(batch_aggregate_edges, lines, stuff_id_mapping, all_stuff_info, show_stuff_codes)

        # Render parallel combine edges (branch outputs → combined output) with dashed styling
        # Same approach: use stuff digests to connect stuff-to-stuff.
        parallel_combine_edges = [edge for edge in graph.edges if edge.kind.is_parallel_combine]
        if parallel_combine_edges:
            lines.append("")
            lines.append("    %% Parallel combine edges: branch outputs → combined output")
            cls._render_dashed_edges(parallel_combine_edges, lines, stuff_id_mapping, all_stuff_info, show_stuff_codes)

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
    def _render_dashed_edges(
        cls,
        edges: list[EdgeSpec],
        lines: list[str],
        stuff_id_mapping: dict[str, str],
        all_stuff_info: dict[str, tuple[str, str | None]],
        show_stuff_codes: bool,
    ) -> None:
        """Render dashed edges between stuff nodes, resolving missing stuff nodes on the fly.

        This handles BATCH_ITEM, BATCH_AGGREGATE, and PARALLEL_COMBINE edges which all share
        the same rendering logic: look up source/target stuff IDs, render any missing stuff
        nodes from all_stuff_info, and emit a dashed arrow with an optional label.

        Args:
            edges: The edges to render as dashed arrows.
            lines: The mermaid output lines list (mutated).
            stuff_id_mapping: Map to store/retrieve stuff mermaid IDs (mutated).
            all_stuff_info: Supplementary stuff info from all nodes including controllers.
            show_stuff_codes: Whether to show digest in stuff labels.
        """
        for edge in edges:
            source_sid = stuff_id_mapping.get(edge.source_stuff_digest) if edge.source_stuff_digest else None
            target_sid = stuff_id_mapping.get(edge.target_stuff_digest) if edge.target_stuff_digest else None
            # Render missing stuff nodes on the fly
            if not source_sid and edge.source_stuff_digest and edge.source_stuff_digest in all_stuff_info:
                name, concept = all_stuff_info[edge.source_stuff_digest]
                lines.append(
                    cls._render_stuff_node(
                        digest=edge.source_stuff_digest,
                        name=name,
                        concept=concept,
                        stuff_id_mapping=stuff_id_mapping,
                        show_stuff_codes=show_stuff_codes,
                        indent="    ",
                    )
                )
                source_sid = stuff_id_mapping.get(edge.source_stuff_digest)
            if not target_sid and edge.target_stuff_digest and edge.target_stuff_digest in all_stuff_info:
                name, concept = all_stuff_info[edge.target_stuff_digest]
                lines.append(
                    cls._render_stuff_node(
                        digest=edge.target_stuff_digest,
                        name=name,
                        concept=concept,
                        stuff_id_mapping=stuff_id_mapping,
                        show_stuff_codes=show_stuff_codes,
                        indent="    ",
                    )
                )
                target_sid = stuff_id_mapping.get(edge.target_stuff_digest)
            if source_sid and target_sid:
                label = edge.label or ""
                if label:
                    lines.append(f'    {source_sid} -."{label}".-> {target_sid}')
                else:
                    lines.append(f"    {source_sid} -.-> {target_sid}")

    @classmethod
    def _render_subgraph_recursive(
        cls,
        node_id: str,
        nodes_by_id: dict[str, NodeSpec],
        id_mapping: dict[str, str],
        children_map: dict[str, list[str]],
        stuff_registry: dict[str, tuple[str, str | None]],
        stuff_producers: dict[str, str],
        stuff_consumers: dict[str, list[str]],
        stuff_id_mapping: dict[str, str],
        subgraph_depths: dict[str, int],
        show_stuff_codes: bool,
        rendered_orphan_stuffs: set[str],
        controller_output_stuffs: dict[str, dict[str, tuple[str, str | None]]],
        indent_level: int = 1,
        depth: int = 0,
    ) -> list[str]:
        """Recursively render pipes and their produced stuff within controller subgraphs.

        This renders both pipe nodes and their produced stuff nodes inside subgraphs.
        Orphan stuffs (no producer) consumed by leaf nodes are also rendered inside
        the same subgraph as their consumer, enabling proper placement of batch item stuffs.
        Controller output stuffs (e.g., parallel_combine targets) are rendered inside
        their controller's subgraph.

        Args:
            node_id: The node to render.
            nodes_by_id: Map of node_id to NodeSpec.
            id_mapping: Map of node_id to sanitized Mermaid ID.
            children_map: Map of parent node_id to list of child node_ids.
            stuff_registry: Map of digest to (name, concept) for all stuffs.
            stuff_producers: Map of digest to producer node_id.
            stuff_consumers: Map of digest to list of consumer node_ids.
            stuff_id_mapping: Map to store stuff mermaid IDs (mutated).
            subgraph_depths: Map to track subgraph IDs and their depths (mutated).
            show_stuff_codes: Whether to show digest in stuff labels.
            rendered_orphan_stuffs: Set of orphan stuff digests already rendered (mutated).
            controller_output_stuffs: Map of controller node_id to {digest: (name, concept)} for stuffs to render inside.
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
                    stuff_consumers=stuff_consumers,
                    stuff_id_mapping=stuff_id_mapping,
                    subgraph_depths=subgraph_depths,
                    show_stuff_codes=show_stuff_codes,
                    rendered_orphan_stuffs=rendered_orphan_stuffs,
                    controller_output_stuffs=controller_output_stuffs,
                    indent_level=indent_level + 1,
                    depth=depth + 1,
                )
                lines.extend(child_lines)

            # Render controller output stuffs (e.g., parallel_combine targets) inside the subgraph
            for digest, (name, concept) in sorted(controller_output_stuffs.get(node_id, {}).items(), key=lambda item: item[1][0]):
                if digest not in stuff_id_mapping:
                    stuff_line = cls._render_stuff_node(
                        digest=digest,
                        name=name,
                        concept=concept,
                        stuff_id_mapping=stuff_id_mapping,
                        show_stuff_codes=show_stuff_codes,
                        indent=indent + "    ",
                    )
                    lines.append(stuff_line)
                    rendered_orphan_stuffs.add(digest)

            lines.append(f"{indent}end")
        else:
            # Leaf node - render as simple node
            lines.append(cls._render_node(node, mermaid_id, indent))

            # Render batch item stuffs (no producer, with -branch-N suffix) consumed by this node
            # This ensures batch item stuffs are placed inside the batch controller's subgraph
            # rather than appearing as orphan "pipeline inputs" at the top level
            for digest, consumer_node_ids in stuff_consumers.items():
                if node_id in consumer_node_ids and digest not in stuff_producers:
                    # Only move stuffs that look like batch items (have -branch- suffix)
                    # Regular pipeline inputs should stay at top level
                    if "-branch-" not in digest:
                        continue
                    # This is a batch item stuff consumed by this node
                    if digest in stuff_registry and digest not in rendered_orphan_stuffs:
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
                        rendered_orphan_stuffs.add(digest)

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
