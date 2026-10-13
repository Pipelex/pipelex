"""The SELECTED_OUTCOME edge of a live condition, which both graph builders derive by this one rule.

A live `PipeCondition` records its resolution, and then starts the pipe of the outcome it chose under its own node. The
edge from the condition to that pipe is derived from those two facts once the graph is built, never drawn by the tracer
the chosen pipe starts under: in a distributed run that pipe can start in another workflow, under a tracer of its own
that never saw the resolution, and the event-replay assembler reads both facts from the run's events whichever tracer
wrote them. The in-process tracer and the assembler derive the edge through `derive_selected_outcome_edges`, so the two
graphs of one run carry the same edges.
"""

from collections.abc import Mapping
from typing import NamedTuple


class SelectedOutcomeEdge(NamedTuple):
    """An edge from a live condition to a pipe it ran, the pipe of the outcome it chose."""

    condition_node_id: str
    outcome_node_id: str
    selected_outcome: str | None
    """The outcome-map key the condition matched, which labels the edge, or None when it took its default outcome."""


def derive_selected_outcome_edges(
    *,
    resolutions: Mapping[str, str | None],
    parent_by_node: Mapping[str, str | None],
) -> list[SelectedOutcomeEdge]:
    """The SELECTED_OUTCOME edges of a graph, one to each pipe started under a resolved condition.

    A live condition starts no pipe but the one of the outcome it chose, and an outcome mapped to `continue` or `fail`
    starts none, so every pipe whose parent is a resolved condition is the pipe of its chosen outcome. A dry run resolves
    no condition, so its graph has no such edge.

    Args:
        resolutions: The selected outcome of each resolved condition, by the condition's node ID: the outcome-map key
            the value it rendered matched, or None when it took its default outcome.
        parent_by_node: The parent node ID of every node of the graph, None for a root, in the order the builder holds
            its nodes.

    Returns:
        The edges, in the order of their target nodes in `parent_by_node`.
    """
    edges: list[SelectedOutcomeEdge] = []
    for node_id, parent_node_id in parent_by_node.items():
        if parent_node_id is None or parent_node_id not in resolutions:
            continue
        edges.append(
            SelectedOutcomeEdge(
                condition_node_id=parent_node_id,
                outcome_node_id=node_id,
                selected_outcome=resolutions[parent_node_id],
            )
        )
    return edges
