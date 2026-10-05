"""One output stuff for a dry-run condition: the record a condition leaves, and the rewrite applying it.

A dry run of a `PipeCondition` runs every outcome, since it cannot know which one a live run would
take, and each outcome writes its own stuff into the condition's one slot. The step after the
condition reads the last outcome's stuff, which is the condition's own output. To draw the
condition's result as one stuff that every outcome produces, the condition records which digests
its outcomes minted, and the graph builders move them onto its output digest once the graph is
built. One function for both builders (the in-process `GraphTracer` and the event-replay
`GraphSpecAssembler`) so the two cannot drift.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from pipelex.graph.graphspec import EdgeSpec, GraphSpec, IOSpec, NodeSpec


class ConditionOutputTyping(BaseModel):
    """The typing of a condition's shared output stuff, when its outcomes do not agree on one.

    Its multiplicity is `True` for a list and never an item count, as every io item records it
    (`stuff_io_multiplicity`), so the shared stuff reads the same on the condition and on the
    steps that read it.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    concept: str
    multiplicity: bool | None = None


class ConditionOutputMerge(BaseModel):
    """The outcome digests a dry-run condition merges onto its own output digest.

    Attributes:
        condition_node_id: The condition's graph node.
        shared_digest: The condition's output digest, which is the last outcome's stuff.
        merged_digests: The digests the other outcomes minted for the same slot.
        shared_typing: The typing of the condition's own output item, set when the outcomes write or
            declare different concepts or multiplicities, so that the shared stuff carries the
            declaration that covers every outcome rather than whichever outcome ran last.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    condition_node_id: str
    shared_digest: str
    merged_digests: list[str] = Field(default_factory=list)
    shared_typing: ConditionOutputTyping | None = None


def apply_condition_output_merges(*, graph: GraphSpec, merges: Sequence[ConditionOutputMerge]) -> GraphSpec:
    """Move every merged digest onto its condition's output digest, across every io item and edge.

    A merged digest is resolved transitively, so a condition run as another condition's outcome
    lands on the outer condition's digest. Each io item keeps its own concept, multiplicity and
    data, except the condition's own output item when its merge carries a typing. Applied once the
    graph is built, the rewrite does not depend on the order the merges were recorded in.
    """
    if not merges:
        return graph

    renames: dict[str, str] = {}
    for merge in merges:
        for merged_digest in merge.merged_digests:
            if merged_digest != merge.shared_digest:
                renames[merged_digest] = merge.shared_digest
    # A typing names the condition's item by the digest it carried when the merge was recorded.
    typings: dict[tuple[str, str], ConditionOutputTyping] = {
        (merge.condition_node_id, merge.shared_digest): merge.shared_typing for merge in merges if merge.shared_typing is not None
    }

    return graph.model_copy(
        update={
            "nodes": [_rewrite_node(node=node, renames=renames, typings=typings) for node in graph.nodes],
            "edges": [_rewrite_edge(edge=edge, renames=renames) for edge in graph.edges],
        }
    )


def _resolve_digest(*, digest: str | None, renames: dict[str, str]) -> str | None:
    """Follow the renames from `digest` to the digest it finally lands on."""
    visited: set[str] = set()
    current = digest
    while current is not None and current in renames and current not in visited:
        visited.add(current)
        current = renames[current]
    return current


def _rewrite_item(*, item: IOSpec, renames: dict[str, str], typing: ConditionOutputTyping | None) -> IOSpec:
    update: dict[str, object] = {"digest": _resolve_digest(digest=item.digest, renames=renames)}
    if typing is not None:
        update["concept"] = typing.concept
        update["multiplicity"] = typing.multiplicity
    return item.model_copy(update=update)


def _rewrite_node(*, node: NodeSpec, renames: dict[str, str], typings: dict[tuple[str, str], ConditionOutputTyping]) -> NodeSpec:
    inputs = [_rewrite_item(item=item, renames=renames, typing=None) for item in node.node_io.inputs]
    outputs = [
        _rewrite_item(item=item, renames=renames, typing=typings.get((node.node_id, item.digest)) if item.digest is not None else None)
        for item in node.node_io.outputs
    ]
    return node.model_copy(update={"node_io": node.node_io.model_copy(update={"inputs": inputs, "outputs": outputs})})


def _rewrite_edge(*, edge: EdgeSpec, renames: dict[str, str]) -> EdgeSpec:
    return edge.model_copy(
        update={
            "source_stuff_digest": _resolve_digest(digest=edge.source_stuff_digest, renames=renames),
            "target_stuff_digest": _resolve_digest(digest=edge.target_stuff_digest, renames=renames),
        }
    )
