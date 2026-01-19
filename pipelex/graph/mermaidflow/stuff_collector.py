"""Stuff data collection utilities for graph visualization.

This module provides functions to collect IOSpec data from GraphSpec nodes
for use in various graph renderers (Mermaid, ReactFlow, etc.).

All functions produce stuff IDs in the format 's_xxx' which is the standard
format used across graph visualization components.
"""

from typing import Any, Callable, TypeVar

from pipelex.graph.graphspec import GraphSpec, IOSpec
from pipelex.graph.mermaidflow.mermaidflow_utils import make_stuff_id

T = TypeVar("T")


def _collect_stuff_field(
    graph: GraphSpec,
    extractor: Callable[[IOSpec], T | None],
) -> dict[str, T]:
    """Generic collector that iterates all IOSpecs and extracts values.

    Iterates over all nodes in the graph, processing outputs first then inputs.
    For inputs, values are only added if not already captured from an output
    (prevents overwriting producer data with consumer data).

    Note: We collect data from ALL nodes including controllers, because:
    - The root controller has the pipeline inputs with data
    - Controllers also capture their outputs with data

    Args:
        graph: The GraphSpec to extract from.
        extractor: Function that extracts a value from IOSpec, returns None to skip.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to extracted values.
    """
    result: dict[str, T] = {}

    for node in graph.nodes:
        # Collect from outputs first
        for output_io_spec in node.node_io.outputs:
            if output_io_spec.digest:
                value = extractor(output_io_spec)
                if value is not None:
                    result[make_stuff_id(output_io_spec.digest)] = value

        # Collect from inputs (for pipeline inputs without a producer)
        for input_io_spec in node.node_io.inputs:
            if input_io_spec.digest:
                stuff_id = make_stuff_id(input_io_spec.digest)
                # Don't overwrite if already captured from output
                if stuff_id not in result:
                    value = extractor(input_io_spec)
                    if value is not None:
                        result[stuff_id] = value

    return result


def collect_stuff_data(graph: GraphSpec) -> dict[str, Any]:
    """Collect IOSpec.data from all stuff nodes in the graph.

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their IOSpec.data content.
        Only includes entries where data is not None.
    """
    return _collect_stuff_field(graph, lambda io_spec: io_spec.data)


def collect_stuff_data_text(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec.data_text (pre-rendered ASCII text) from all stuff nodes in the graph.

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their text representation.
        Only includes entries where data_text is not None.
    """
    return _collect_stuff_field(graph, lambda io_spec: io_spec.data_text)


def collect_stuff_data_html(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec.data_html (pre-rendered HTML) from all stuff nodes in the graph.

    Args:
        graph: The GraphSpec to extract data from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their HTML representation.
        Only includes entries where data_html is not None.
    """
    return _collect_stuff_field(graph, lambda io_spec: io_spec.data_html)


def collect_stuff_content_type(graph: GraphSpec) -> dict[str, str]:
    """Collect IOSpec content_type from all stuff nodes in the graph.

    This is useful for rendering PDF and other special content types.

    Args:
        graph: The GraphSpec to extract content_type from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their content_type.
        Only includes entries where content_type is not None.
    """
    return _collect_stuff_field(graph, lambda io_spec: io_spec.content_type)


def collect_stuff_metadata(graph: GraphSpec) -> dict[str, dict[str, str]]:
    """Collect IOSpec metadata (name, concept) from all stuff nodes in the graph.

    Args:
        graph: The GraphSpec to extract metadata from.

    Returns:
        Dict mapping stuff IDs (s_xxx format) to their metadata dict with 'name' and 'concept'.
    """

    def extract_metadata(io_spec: IOSpec) -> dict[str, str]:
        meta: dict[str, str] = {"name": io_spec.name}
        if io_spec.concept:
            meta["concept"] = io_spec.concept
        return meta

    return _collect_stuff_field(graph, extract_metadata)
