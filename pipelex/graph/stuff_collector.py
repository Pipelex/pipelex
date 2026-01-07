"""Stuff data collection utilities for graph visualization.

This module provides functions to collect IOSpec data from GraphSpec nodes
for use in various graph renderers (Mermaid, ReactFlow, etc.).

All functions produce stuff IDs in the format 's_xxx' which is the standard
format used across graph visualization components.
"""

from typing import Any

from pipelex import log
from pipelex.graph.graphspec import GraphSpec
from pipelex.tools.mermaid.mermaid_utils import sanitize_mermaid_id


def collect_stuff_data(graph: GraphSpec) -> dict[str, Any]:
    """Collect IOSpec.data from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their IOSpec.data content.
        Only includes entries where data is not None.
    """
    stuff_data: dict[str, Any] = {}

    log.debug(f"collect_stuff_data: {len(graph.nodes)} nodes")

    for node in graph.nodes:
        # Note: We include ALL nodes (including controllers) because they may have data
        # on their inputs (pipeline inputs) or outputs (pipeline outputs)
        log.verbose(f"  Processing node: {node.node_id}, outputs={len(node.node_io.outputs)}, inputs={len(node.node_io.inputs)}")

        # Collect data from outputs
        for output_spec in node.node_io.outputs:
            log.verbose(f"    Output: digest={output_spec.digest}, has_data={output_spec.data is not None}")
            if output_spec.digest and output_spec.data is not None:
                stuff_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                stuff_data[stuff_id] = output_spec.data

        # Collect data from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            log.verbose(f"    Input: digest={input_spec.digest}, has_data={input_spec.data is not None}")
            if input_spec.digest and input_spec.data is not None:
                stuff_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_id not in stuff_data:
                    stuff_data[stuff_id] = input_spec.data

    log.debug(f"collect_stuff_data: collected {len(stuff_data)} stuff items")
    return stuff_data


def collect_stuff_data_text(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec.data_text (pre-rendered ASCII text) from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their text representation.
        Only includes entries where data_text is not None.
    """
    log.debug("collecting stuff data text for graph_spec")
    stuff_data_text: dict[str, str] = {}

    for node in graph.nodes:
        # Collect data_text from outputs
        for output_spec in node.node_io.outputs:
            if output_spec.digest and output_spec.data_text is not None:
                stuff_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                stuff_data_text[stuff_id] = output_spec.data_text

        # Collect data_text from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            if input_spec.digest and input_spec.data_text is not None:
                stuff_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_id not in stuff_data_text:
                    stuff_data_text[stuff_id] = input_spec.data_text

    return stuff_data_text


def collect_stuff_data_html(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec.data_html (pre-rendered HTML) from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their HTML representation.
        Only includes entries where data_html is not None.
    """
    stuff_data_html: dict[str, str] = {}

    for node in graph.nodes:
        # Collect data_html from outputs
        for output_spec in node.node_io.outputs:
            if output_spec.digest and output_spec.data_html is not None:
                stuff_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                stuff_data_html[stuff_id] = output_spec.data_html

        # Collect data_html from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            if input_spec.digest and input_spec.data_html is not None:
                stuff_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_id not in stuff_data_html:
                    stuff_data_html[stuff_id] = input_spec.data_html

    return stuff_data_html


def collect_stuff_metadata(graph: GraphSpec) -> dict[str, dict[str, str]]:
    """Collect IOSpec metadata (name, concept) from all stuff nodes in the graph.

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract metadata from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their metadata dict with 'name' and 'concept'.
    """
    stuff_metadata: dict[str, dict[str, str]] = {}

    for node in graph.nodes:
        # Collect metadata from outputs
        for output_spec in node.node_io.outputs:
            if output_spec.digest:
                stuff_id = f"s_{sanitize_mermaid_id(output_spec.digest)[2:]}"
                meta: dict[str, str] = {"name": output_spec.name}
                if output_spec.concept:
                    meta["concept"] = output_spec.concept
                stuff_metadata[stuff_id] = meta

        # Collect metadata from inputs (for pipeline inputs without a producer)
        for input_spec in node.node_io.inputs:
            if input_spec.digest:
                stuff_id = f"s_{sanitize_mermaid_id(input_spec.digest)[2:]}"
                # Don't overwrite if already captured from output
                if stuff_id not in stuff_metadata:
                    meta = {"name": input_spec.name}
                    if input_spec.concept:
                        meta["concept"] = input_spec.concept
                    stuff_metadata[stuff_id] = meta

    return stuff_metadata
