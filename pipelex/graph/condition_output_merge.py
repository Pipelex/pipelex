"""One output stuff for a dry-run condition: the record a condition leaves, and the rewrite applying it.

A dry run of a `PipeCondition` runs every outcome, since it cannot know which one a live run would
take, and each outcome writes its own stuff into the condition's one slot. The step after the
condition reads the last outcome's stuff, which is the condition's own output. To draw the
condition's result as one stuff that every outcome produces, the condition records which digests
its outcomes minted, and the graph builders move them onto its output digest once the graph is
built. When the outcomes disagree on what they write, the condition also records the typing that
covers them all, and every item carrying the shared stuff outside the outcomes takes it: the
condition's own item, the controllers enclosing the condition whose output it is, and the steps
reading it. One function for both builders (the in-process `GraphTracer` and the event-replay
`GraphSpecAssembler`) so the two cannot drift.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, IOSpec, NodeSpec


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
        shared_typing: The typing of every item carrying the shared stuff outside the condition's
            outcomes, set when the outcomes write or declare different concepts or multiplicities,
            so that the shared stuff carries the declaration that covers every outcome rather than
            whichever outcome ran last.
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
    data, except the items a typed condition covers, which take its typing: on the stuff the
    condition's output resolves to, its own item and every item on a node outside every condition
    merged onto that stuff (the controllers enclosing it, the steps reading it), and, inside
    another condition's outcomes, the items on the nodes enclosing it. An item several typed
    conditions cover takes the outermost one's typing, the earlier in node order at equal depth.
    Applied once the graph is built, the rewrite does not depend on the order the merges were
    recorded in.
    """
    if not merges:
        return graph

    renames: dict[str, str] = {}
    for merge in merges:
        for merged_digest in merge.merged_digests:
            if merged_digest != merge.shared_digest:
                renames[merged_digest] = merge.shared_digest

    shared_typings = _SharedTypings.build(graph=graph, merges=merges, renames=renames)

    return graph.model_copy(
        update={
            "nodes": [_rewrite_node(node=node, renames=renames, shared_typings=shared_typings) for node in graph.nodes],
            "edges": [_rewrite_edge(edge=edge, renames=renames) for edge in graph.edges],
        }
    )


class _TypingScope(BaseModel):
    """A typed condition's place in the containment tree, and the typing it gives."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    condition_node_id: str
    condition_ancestors: frozenset[str]
    rank: tuple[int, int]
    typing: ConditionOutputTyping


class _SharedTypings:
    """Which typed condition, if any, covers an io item, read off the finished graph's containment tree."""

    def __init__(self, *, parents: dict[str, str], conditions_by_digest: dict[str, set[str]], scopes_by_digest: dict[str, list[_TypingScope]]):
        self._parents = parents
        # Every condition merged onto a stuff, typed or not, bounds the outcomes its typing does not reach into.
        self._conditions_by_digest = conditions_by_digest
        self._scopes_by_digest = scopes_by_digest

    @classmethod
    def build(cls, *, graph: GraphSpec, merges: Sequence[ConditionOutputMerge], renames: dict[str, str]) -> "_SharedTypings":
        parents = {edge.target: edge.source for edge in graph.edges if edge.kind == EdgeKind.CONTAINS}
        node_order = {node.node_id: index for index, node in enumerate(graph.nodes)}
        conditions_by_digest: dict[str, set[str]] = {}
        scopes_by_digest: dict[str, list[_TypingScope]] = {}
        for merge in merges:
            digest = _resolve_digest(digest=merge.shared_digest, renames=renames)
            if digest is None:
                continue
            conditions_by_digest.setdefault(digest, set()).add(merge.condition_node_id)
            if merge.shared_typing is None:
                continue
            condition_ancestors = _ancestors(node_id=merge.condition_node_id, parents=parents)
            scopes_by_digest.setdefault(digest, []).append(
                _TypingScope(
                    condition_node_id=merge.condition_node_id,
                    condition_ancestors=frozenset(condition_ancestors),
                    rank=(len(condition_ancestors), node_order.get(merge.condition_node_id, len(node_order))),
                    typing=merge.shared_typing,
                )
            )
        return cls(parents=parents, conditions_by_digest=conditions_by_digest, scopes_by_digest=scopes_by_digest)

    def typing_for(self, *, node_id: str, digest: str | None) -> ConditionOutputTyping | None:
        """The typing of the outermost typed condition covering `node_id`'s item on `digest`, if any.

        A typed condition covers an item on the stuff its output resolves to when the item's node is
        not inside its outcomes. A node inside another condition's outcomes on that stuff is covered
        only when it is the typed condition or encloses it, as an outcome sequence ending on a nested
        condition does: a sibling outcome writes its own value, which no typing describes better.
        """
        if digest is None or digest not in self._scopes_by_digest:
            return None
        node_ancestors = set(_ancestors(node_id=node_id, parents=self._parents))
        inside_an_outcome = not node_ancestors.isdisjoint(self._conditions_by_digest[digest])
        covering = [
            scope
            for scope in self._scopes_by_digest[digest]
            if scope.condition_node_id not in node_ancestors
            and (not inside_an_outcome or scope.condition_node_id == node_id or node_id in scope.condition_ancestors)
        ]
        if not covering:
            return None
        return min(covering, key=lambda scope: scope.rank).typing


def _ancestors(*, node_id: str, parents: dict[str, str]) -> list[str]:
    """The controllers containing `node_id`, innermost first, stopping on a cycle."""
    ancestors: list[str] = []
    current = parents.get(node_id)
    while current is not None and current != node_id and current not in ancestors:
        ancestors.append(current)
        current = parents.get(current)
    return ancestors


def _resolve_digest(*, digest: str | None, renames: dict[str, str]) -> str | None:
    """Follow the renames from `digest` to the digest it finally lands on."""
    visited: set[str] = set()
    current = digest
    while current is not None and current in renames and current not in visited:
        visited.add(current)
        current = renames[current]
    return current


def _rewrite_item(*, item: IOSpec, node_id: str, renames: dict[str, str], shared_typings: _SharedTypings) -> IOSpec:
    digest = _resolve_digest(digest=item.digest, renames=renames)
    update: dict[str, object] = {"digest": digest}
    typing = shared_typings.typing_for(node_id=node_id, digest=digest)
    if typing is not None:
        update["concept"] = typing.concept
        update["multiplicity"] = typing.multiplicity
    return item.model_copy(update=update)


def _rewrite_node(*, node: NodeSpec, renames: dict[str, str], shared_typings: _SharedTypings) -> NodeSpec:
    inputs = [_rewrite_item(item=item, node_id=node.node_id, renames=renames, shared_typings=shared_typings) for item in node.node_io.inputs]
    outputs = [_rewrite_item(item=item, node_id=node.node_id, renames=renames, shared_typings=shared_typings) for item in node.node_io.outputs]
    return node.model_copy(update={"node_io": node.node_io.model_copy(update={"inputs": inputs, "outputs": outputs})})


def _rewrite_edge(*, edge: EdgeSpec, renames: dict[str, str]) -> EdgeSpec:
    return edge.model_copy(
        update={
            "source_stuff_digest": _resolve_digest(digest=edge.source_stuff_digest, renames=renames),
            "target_stuff_digest": _resolve_digest(digest=edge.target_stuff_digest, renames=renames),
        }
    )
