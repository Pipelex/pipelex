"""Mermaid flowchart exporter for GraphSpec.

This module converts GraphSpec to Mermaid flowchart syntax, using subgraphs
to represent controller containment relationships.

The module uses GraphAnalysis for pre-computed graph analysis, avoiding
duplicated analysis logic across different rendering functions.
"""

import operator
from typing import Any

from pydantic import BaseModel

from pipelex import log
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graph_config import GraphConfig
from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    GraphSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
)
from pipelex.tools.mermaid.mermaid_utils import escape_mermaid_label, sanitize_mermaid_id
from pipelex.tools.misc.chart_utils import FlowchartDirection


class MermaidOutput(BaseModel):
    """Mermaid code paired with optional stuff data for interactive HTML rendering.

    Attributes:
        mermaid_code: The generated Mermaid flowchart syntax.
        stuff_data: Optional mapping from stuff mermaid IDs to their full IOSpec.data content.
            Only populated when GraphConfig.data_inclusion.stuff_json_content is True.
        stuff_data_text: Optional mapping from stuff mermaid IDs to their ASCII text representation.
            Only populated when GraphConfig.data_inclusion.stuff_text_content is True.
        stuff_data_html: Optional mapping from stuff mermaid IDs to their HTML representation.
            Only populated when GraphConfig.data_inclusion.stuff_html_content is True.
        stuff_metadata: Optional mapping from stuff mermaid IDs to their display metadata (name, concept).
            Always populated when any stuff data is present.
    """

    mermaid_code: str
    stuff_data: dict[str, Any] | None = None
    stuff_data_text: dict[str, str] | None = None
    stuff_data_html: dict[str, str] | None = None
    stuff_metadata: dict[str, dict[str, str]] | None = None


# Light pastel colors for subgraph depth coloring (cycles through these)
SUBGRAPH_DEPTH_COLORS = [
    "#e6f3ff",  # Light blue
    "#e6ffe6",  # Light green
    "#fffde6",  # Light yellow
    "#ffe6f0",  # Light pink
    "#f0e6ff",  # Light purple
    "#fff3e6",  # Light orange
]


def _get_node_label(node: NodeSpec) -> str:
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


def _collect_stuff_data(graph: GraphSpec) -> dict[str, Any]:
    """Collect IOSpec.data from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff mermaid IDs (s_xxx format) to their IOSpec.data content.
        Only includes entries where data is not None.
    """
    stuff_data: dict[str, Any] = {}

    log.debug(f"_collect_stuff_data: {len(graph.nodes)} nodes")

    for node in graph.nodes:
        # Note: We include ALL nodes (including controllers) because they may have data
        # on their inputs (pipeline inputs) or outputs (pipeline outputs)
        log.verbose(f"  Processing node: {node.node_id}, outputs={len(node.node_io.outputs)}, inputs={len(node.node_io.inputs)}")

        # Collect data from outputs
        for output_spec in node.node_io.outputs:
            log.verbose(f"    Output: digest={output_spec.digest}, has_data={output_spec.data is not None}")
            if output_spec.digest and output_spec.data is not None:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                stuff_data[stuff_mermaid_id] = output_spec.data

        # Collect data from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            log.verbose(f"    Input: digest={input_spec.digest}, has_data={input_spec.data is not None}")
            if input_spec.digest and input_spec.data is not None:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_mermaid_id not in stuff_data:
                    stuff_data[stuff_mermaid_id] = input_spec.data

    log.debug(f"_collect_stuff_data: collected {len(stuff_data)} stuff items")
    return stuff_data


def collect_stuff_data_text(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec.data_text (pre-rendered ASCII text) from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff mermaid IDs (s_xxx format) to their text representation.
        Only includes entries where data_text is not None.
    """
    log.debug("collecting stuff data text for graph_spec")
    stuff_data_text: dict[str, str] = {}

    for node in graph.nodes:
        # Collect data_text from outputs
        for output_spec in node.node_io.outputs:
            if output_spec.digest and output_spec.data_text is not None:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                stuff_data_text[stuff_mermaid_id] = output_spec.data_text

        # Collect data_text from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            if input_spec.digest and input_spec.data_text is not None:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_mermaid_id not in stuff_data_text:
                    stuff_data_text[stuff_mermaid_id] = input_spec.data_text

    return stuff_data_text


def collect_stuff_data_html(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec.data_html (pre-rendered HTML) from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff mermaid IDs (s_xxx format) to their HTML representation.
        Only includes entries where data_html is not None.
    """
    stuff_data_html: dict[str, str] = {}

    for node in graph.nodes:
        # Collect data_html from outputs
        for output_spec in node.node_io.outputs:
            if output_spec.digest and output_spec.data_html is not None:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                stuff_data_html[stuff_mermaid_id] = output_spec.data_html

        # Collect data_html from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            if input_spec.digest and input_spec.data_html is not None:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_mermaid_id not in stuff_data_html:
                    stuff_data_html[stuff_mermaid_id] = input_spec.data_html

    return stuff_data_html


def collect_stuff_metadata(graph: GraphSpec) -> dict[str, dict[str, str]]:
    """Collect IOSpec metadata (name, concept) from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract metadata from.

    Returns:
        Dict mapping stuff mermaid IDs (s_xxx format) to their metadata dict with 'name' and 'concept'.
    """
    stuff_metadata: dict[str, dict[str, str]] = {}

    for node in graph.nodes:
        # Collect metadata from outputs
        for output_spec in node.node_io.outputs:
            if output_spec.digest:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                meta: dict[str, str] = {"name": output_spec.name}
                if output_spec.concept:
                    meta["concept"] = output_spec.concept
                stuff_metadata[stuff_mermaid_id] = meta

        # Collect metadata from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            if input_spec.digest:
                stuff_mermaid_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_mermaid_id not in stuff_metadata:
                    meta = {"name": input_spec.name}
                    if input_spec.concept:
                        meta["concept"] = input_spec.concept
                    stuff_metadata[stuff_mermaid_id] = meta

    return stuff_metadata


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


def _render_stuff_node(
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
    stuff_mermaid_id = f"s_{sanitize_mermaid_id(digest)[2:]}"
    stuff_id_mapping[digest] = stuff_mermaid_id

    # Build label
    if show_stuff_codes:
        label = f"{escape_mermaid_label(name)} ({digest[:5]})"
    else:
        label = escape_mermaid_label(name)

    if concept:
        label = f"{label}<br/>{escape_mermaid_label(concept)}"

    return f'{indent}{stuff_mermaid_id}(["{label}"]):::stuff'


def _render_combo_subgraph_recursive(
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
        label = _get_node_label(node)
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
            child_lines = _render_combo_subgraph_recursive(
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
        lines.append(_render_node(node, mermaid_id, indent))

        # Also render any stuff nodes produced by this pipe
        for digest, producer_node_id in stuff_producers.items():
            if producer_node_id == node_id and digest in stuff_registry:
                name, concept = stuff_registry[digest]
                stuff_line = _render_stuff_node(
                    digest=digest,
                    name=name,
                    concept=concept,
                    stuff_id_mapping=stuff_id_mapping,
                    show_stuff_codes=show_stuff_codes,
                    indent=indent,
                )
                lines.append(stuff_line)

    return lines


def _render_subgraph_recursive(
    node_id: str,
    nodes_by_id: dict[str, NodeSpec],
    id_mapping: dict[str, str],
    children_map: dict[str, list[str]],
    edges: list[EdgeSpec],
    include_data_edges: bool,
    include_selected_outcome_edges: bool,
    subgraph_depths: dict[str, int],
    indent_level: int = 1,
    depth: int = 0,
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
        subgraph_depths: Map to track subgraph IDs and their depths (mutated).
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
        label = _get_node_label(node)
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
            child_lines = _render_subgraph_recursive(
                node_id=child_id,
                nodes_by_id=nodes_by_id,
                id_mapping=id_mapping,
                children_map=children_map,
                edges=edges,
                include_data_edges=include_data_edges,
                include_selected_outcome_edges=include_selected_outcome_edges,
                subgraph_depths=subgraph_depths,
                indent_level=indent_level + 1,
                depth=depth + 1,
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
    controller_node_ids: set[str] | None = None,
) -> list[str]:
    """Render edges in Mermaid syntax.

    Args:
        edges: List of all edges.
        id_mapping: Map of node_id to sanitized Mermaid ID.
        include_data_edges: Whether to include DATA edges.
        include_contains_edges: Whether to include CONTAINS edges as arrows.
        include_selected_outcome_edges: Whether to include SELECTED_OUTCOME edges.
        controller_node_ids: Set of node IDs that are controllers with children (rendered as subgraphs).

    Returns:
        List of Mermaid edge declaration lines.
    """
    lines: list[str] = []
    controller_ids = controller_node_ids or set()

    # Sort edges for deterministic output
    sorted_edges = sorted(edges, key=lambda edge: (edge.kind, edge.source, edge.target, edge.label or ""))

    for edge in sorted_edges:
        # Skip edges to/from controllers (they are subgraphs, not nodes)
        if edge.source in controller_ids or edge.target in controller_ids:
            continue

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


def graphspec_to_orchestration_mermaid(
    graph: GraphSpec,
    *,
    direction: FlowchartDirection | None = None,
    include_data_edges: bool = True,
    include_contains_edges: bool = False,
    include_selected_outcome_edges: bool = True,
) -> str:
    """Convert a GraphSpec to Mermaid flowchart syntax.

    Args:
        graph: The GraphSpec to convert.
        direction: Flowchart direction. Defaults to TOP_DOWN if not specified.
        include_data_edges: Whether to render DATA edges as dashed arrows.
        include_contains_edges: Whether to render CONTAINS as explicit arrows
            instead of subgraphs. Defaults to False (use subgraphs).
        include_selected_outcome_edges: Whether to render SELECTED_OUTCOME edges.

    Returns:
        Mermaid flowchart syntax as a string.
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

    # Track subgraph depths for coloring
    subgraph_depths: dict[str, int] = {}

    # Render nodes (using subgraphs for containment)
    for root_node in analysis.root_nodes:
        node_lines = _render_subgraph_recursive(
            node_id=root_node.node_id,
            nodes_by_id=analysis.nodes_by_id,
            id_mapping=id_mapping,
            children_map=analysis.containment_tree,
            edges=graph.edges,
            include_data_edges=include_data_edges,
            include_selected_outcome_edges=include_selected_outcome_edges,
            subgraph_depths=subgraph_depths,
        )
        lines.extend(node_lines)

    # Render edges
    edge_lines = _render_edges(
        edges=graph.edges,
        id_mapping=id_mapping,
        include_data_edges=include_data_edges,
        include_contains_edges=include_contains_edges,
        include_selected_outcome_edges=include_selected_outcome_edges,
        controller_node_ids=analysis.controller_node_ids,
    )
    if edge_lines:
        lines.append("")  # Blank line before edges
        lines.extend(edge_lines)

    # Style definitions
    lines.append("")
    lines.append("    %% Style definitions")
    lines.append("    classDef failed fill:#ffcccc,stroke:#cc0000")
    lines.append("    classDef controller fill:#e6f3ff,stroke:#0066cc")

    # Apply depth-based colors to subgraphs
    if subgraph_depths:
        lines.append("")
        lines.append("    %% Subgraph depth-based coloring")
        for subgraph_id, sg_depth in sorted(subgraph_depths.items()):
            color = SUBGRAPH_DEPTH_COLORS[sg_depth % len(SUBGRAPH_DEPTH_COLORS)]
            lines.append(f"    style {subgraph_id} fill:{color}")

    return "\n".join(lines)


def graphspec_to_dataflow_mermaid(
    graph: GraphSpec,
    graph_config: GraphConfig,
    *,
    direction: FlowchartDirection | None = None,
    show_stuff_codes: bool = False,
) -> MermaidOutput:
    """Convert a GraphSpec to a data-lineage focused Mermaid flowchart.

    Unlike graphspec_to_mermaid (which shows orchestration/containment),
    this shows how data (Stuff objects) flow between pipes.

    The diagram shows:
    - Pipe nodes as blue rectangles
    - Stuff nodes as orange pills (representing data items)
    - Edges from producer pipes to stuff, and from stuff to consumer pipes

    Args:
        graph: The GraphSpec to convert.
        graph_config: Configuration controlling data inclusion and rendering options.
        direction: Flowchart direction. Defaults to TOP_DOWN if not specified.
        show_stuff_codes: Whether to show stuff_code (digest) in stuff labels.

    Returns:
        MermaidOutput containing mermaid code and optional stuff data mapping.
    """
    effective_direction = direction or FlowchartDirection.TOP_DOWN
    lines: list[str] = []

    # Pre-compute graph analysis
    analysis = GraphAnalysis.from_graphspec(graph)

    # Header
    lines.append(f"flowchart {effective_direction.mermaid_code}")

    # Build ID mapping for pipe nodes
    pipe_id_mapping: dict[str, str] = {}
    for node in graph.nodes:
        pipe_id_mapping[node.node_id] = sanitize_mermaid_id(node.node_id)

    # Skip if no data flow information
    if not analysis.has_data_flow_info():
        lines.append("    %% No data flow information available")
        lines.append("    note[No IOSpec data captured. Run with data flow tracing enabled.]")
        mermaid_code = "\n".join(lines)
        return MermaidOutput(mermaid_code=mermaid_code, stuff_data=None)

    # Build stuff registry as tuple format for compatibility with rendering code
    stuff_registry: dict[str, tuple[str, str | None]] = {}
    for digest, stuff_info in analysis.stuff_registry.items():
        stuff_registry[digest] = (stuff_info.name, stuff_info.concept)

    # Render pipe nodes
    lines.append("    %% Pipe nodes")
    rendered_pipes: set[str] = set()

    # Only render pipes that participate in data flow
    participating_pipes: set[str] = set(analysis.stuff_producers.values())
    for consumers in analysis.stuff_consumers.values():
        participating_pipes.update(consumers)

    for node in sorted(graph.nodes, key=lambda n_iter: (n_iter.pipe_code or "", n_iter.node_id)):
        if node.node_id not in participating_pipes:
            continue
        if node.node_id in rendered_pipes:
            continue

        mermaid_id = pipe_id_mapping[node.node_id]
        label = _get_node_label(node)
        if node.status == NodeStatus.FAILED:
            lines.append(f'    {mermaid_id}["{label}"]:::pipe_failed')
        else:
            lines.append(f'    {mermaid_id}["{label}"]:::pipe')
        rendered_pipes.add(node.node_id)

    # Render stuff nodes
    lines.append("")
    lines.append("    %% Stuff nodes (data items)")
    stuff_id_mapping: dict[str, str] = {}

    for digest, (name, concept) in sorted(stuff_registry.items(), key=lambda item: item[1][0]):
        stuff_mermaid_id = f"s_{sanitize_mermaid_id(digest)[2:]}"  # Use s_ prefix for stuff
        stuff_id_mapping[digest] = stuff_mermaid_id

        # Build label
        if show_stuff_codes:
            label = f"{escape_mermaid_label(name)} ({digest[:5]})"
        else:
            label = escape_mermaid_label(name)

        if concept:
            label = f"{label}<br/>{escape_mermaid_label(concept)}"

        # Stuff nodes as pills (stadium shape)
        lines.append(f'    {stuff_mermaid_id}(["{label}"]):::stuff')

    # Render edges: producer -> stuff
    lines.append("")
    lines.append("    %% Data flow edges: producer -> stuff -> consumer")

    for digest, producer_node_id in sorted(analysis.stuff_producers.items(), key=operator.itemgetter(0)):
        producer_mermaid_id = pipe_id_mapping.get(producer_node_id)
        prod_stuff_mermaid_id = stuff_id_mapping.get(digest)
        if producer_mermaid_id and prod_stuff_mermaid_id:
            lines.append(f"    {producer_mermaid_id} --> {prod_stuff_mermaid_id}")

    # Render edges: stuff -> consumer
    for digest, consumer_node_ids in sorted(analysis.stuff_consumers.items(), key=operator.itemgetter(0)):
        cons_stuff_mermaid_id = stuff_id_mapping.get(digest)
        if not cons_stuff_mermaid_id:
            continue
        for consumer_node_id in sorted(consumer_node_ids):
            consumer_mermaid_id = pipe_id_mapping.get(consumer_node_id)
            if consumer_mermaid_id:
                lines.append(f"    {cons_stuff_mermaid_id} --> {consumer_mermaid_id}")

    # Style definitions
    lines.append("")
    lines.append("    %% Style definitions")
    lines.append("    classDef pipe fill:#e6f3ff,stroke:#0066cc")
    lines.append("    classDef pipe_failed fill:#ffcccc,stroke:#cc0000")
    lines.append("    classDef stuff fill:#fff3e6,stroke:#cc6600,stroke-width:2px")

    mermaid_code = "\n".join(lines)

    # Collect stuff data in configured formats
    stuff_data: dict[str, Any] | None = None
    stuff_data_text: dict[str, str] | None = None
    stuff_data_html: dict[str, str] | None = None

    if graph_config.data_inclusion.stuff_json_content:
        log.debug("collecting stuff data json for graph_spec")
        stuff_data = _collect_stuff_data(graph=graph)
    else:
        log.debug("no stuff data json to collect for graph_spec")
    if graph_config.data_inclusion.stuff_text_content:
        log.debug("collecting stuff data text for graph_spec")
        stuff_data_text = collect_stuff_data_text(graph=graph)
    else:
        log.debug("no stuff data text to collect for graph_spec")
    if graph_config.data_inclusion.stuff_html_content:
        log.debug("collecting stuff data html for graph_spec")
        stuff_data_html = collect_stuff_data_html(graph=graph)
    else:
        log.debug("no stuff data html to collect for graph_spec")

    # Collect metadata if any stuff data is present
    stuff_metadata: dict[str, dict[str, str]] | None = None
    if stuff_data or stuff_data_text or stuff_data_html:
        stuff_metadata = collect_stuff_metadata(graph=graph)

    return MermaidOutput(
        mermaid_code=mermaid_code,
        stuff_data=stuff_data,
        stuff_data_text=stuff_data_text,
        stuff_data_html=stuff_data_html,
        stuff_metadata=stuff_metadata,
    )


def graphspec_to_combo_mermaid(
    graph: GraphSpec,
    graph_config: GraphConfig,
    *,
    direction: FlowchartDirection | None = None,
    show_stuff_codes: bool = False,
    include_subgraphs: bool = True,
) -> MermaidOutput:
    """Convert a GraphSpec to a combined data-flow and orchestration Mermaid flowchart.

    This view combines the best of both worlds:
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
        MermaidOutput containing mermaid code and optional stuff data mapping.
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
        return MermaidOutput(mermaid_code=mermaid_code, stuff_data=None)

    if include_subgraphs:
        # Render pipe nodes and their produced stuff within controller subgraphs
        lines.append("")
        lines.append("    %% Pipe and stuff nodes within controller subgraphs")
        for root_node in analysis.root_nodes:
            node_lines = _render_combo_subgraph_recursive(
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
                stuff_line = _render_stuff_node(
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
            label = _get_node_label(node)
            if node.status == NodeStatus.FAILED:
                lines.append(f'    {mermaid_id}["{label}"]:::pipe_failed')
            else:
                lines.append(f'    {mermaid_id}["{label}"]:::pipe')

        # Render all stuff nodes flat at top level
        lines.append("")
        lines.append("    %% Stuff nodes (data items)")
        for digest, (name, concept) in sorted(stuff_registry.items(), key=lambda item: item[1][0]):
            stuff_line = _render_stuff_node(
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
        stuff_data = _collect_stuff_data(graph=graph)
    if graph_config.data_inclusion.stuff_text_content:
        stuff_data_text = collect_stuff_data_text(graph=graph)
    if graph_config.data_inclusion.stuff_html_content:
        stuff_data_html = collect_stuff_data_html(graph=graph)

    # Collect metadata if any stuff data is present
    stuff_metadata: dict[str, dict[str, str]] | None = None
    if stuff_data or stuff_data_text or stuff_data_html:
        stuff_metadata = collect_stuff_metadata(graph=graph)

    return MermaidOutput(
        mermaid_code=mermaid_code,
        stuff_data=stuff_data,
        stuff_data_text=stuff_data_text,
        stuff_data_html=stuff_data_html,
        stuff_metadata=stuff_metadata,
    )
