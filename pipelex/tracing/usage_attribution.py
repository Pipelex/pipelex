"""Attribution of inference usage to graph nodes.

One event stream, two projections. ``UsageAggregator`` projects ``UsageReportEvent``
into the flat, client-facing ``tokens_usages`` list (``node_id`` dropped, one record per
call). This module projects the SAME events into per-node totals for the GraphSpec
(``node_id`` kept, calls folded together). Keeping the arithmetic here — rather than
inline in ``_AssemblerState`` — means the ``NodeUsageSpec`` invariants live in exactly
one place, and cost is never re-derived: every dollar comes from
``compute_tokens_usage_cost``, the same call the cost report uses.
"""

from collections.abc import Mapping

from pipelex import log
from pipelex.cogt.usage.cost_registry import compute_tokens_usage_costs
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import ModelUsageSpec, NodeUsageSpec
from pipelex.reporting.reporting_types import AnyTokensUsage


class _ModelTotals:
    """One model's running totals inside a UsageAccumulator."""

    def __init__(self) -> None:
        self.inference_calls: int = 0
        self.rated_inference_calls: int = 0
        self.cost: float | None = None

    def absorb(self, *, other: "_ModelTotals") -> None:
        self.inference_calls += other.inference_calls
        self.rated_inference_calls += other.rated_inference_calls
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost


class UsageAccumulator:
    """A running total of inference usage — for one node, or for a rollup of many.

    Mutable and internal: it exists so folding a call and merging a subtree share one
    definition of every number. ``NodeUsageSpec`` is the immutable output shape and owns
    the invariants; this class is what upholds them:

      - ``rated_inference_calls`` counts only the calls that carried a rate table, so a
        node with mixed rated/unrated calls reports a cost that is explicitly a lower
        bound instead of a total masquerading as complete (invariant 3).
      - ``cost`` stays ``None`` until the first rated call, so unrated never renders as
        ``$0.00`` (invariant 2).
      - ``total_tokens`` is accumulated as input_joined + output, never as a sum over
        ``nb_tokens_by_category`` — ``input_cached`` is a subset of ``input`` and
        summing double-counts (invariant 4).
      - ``by_model`` keys on (name, id) so the models that actually RAN are kept
        distinct, rather than collapsed into one that would be wrong whenever a node
        used two — which a PipeLLM does routinely, its text pass and its object pass
        resolving separately (invariant 5).
    """

    def __init__(self) -> None:
        self.inference_calls: int = 0
        self.rated_inference_calls: int = 0
        self.nb_tokens_by_category: dict[str, int] = {}
        self.total_tokens: int = 0
        self.cost: float | None = None
        self.cost_input: float | None = None
        self.cost_output: float | None = None
        # (inference_model_name, inference_model_id, model_type) -> that model's totals.
        self.by_model: dict[tuple[str, str, str], _ModelTotals] = {}

    def fold(self, *, tokens_usage: AnyTokensUsage) -> None:
        """Fold one inference call's usage into this total."""
        self.inference_calls += 1
        for token_category, nb_tokens in tokens_usage.nb_tokens_by_category.items():
            self.nb_tokens_by_category[token_category] = self.nb_tokens_by_category.get(token_category, 0) + nb_tokens

        nb_tokens_input_joined = tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT, 0)
        nb_tokens_output = tokens_usage.nb_tokens_by_category.get(TokenCategory.OUTPUT, 0)
        self.total_tokens += nb_tokens_input_joined + nb_tokens_output

        model_key = (tokens_usage.inference_model_name, tokens_usage.inference_model_id, tokens_usage.model_type)
        model_totals = self.by_model.get(model_key)
        if model_totals is None:
            model_totals = _ModelTotals()
            self.by_model[model_key] = model_totals
        model_totals.inference_calls += 1

        costs = compute_tokens_usage_costs(tokens_usage)
        if costs is None:
            # Unrated call (no rate table: own-GPU model, dry/mock run). It still counts
            # as an inference call, which is what tells "made no call" apart from "made
            # only unrated calls".
            return
        self.rated_inference_calls += 1
        self.cost = (self.cost or 0.0) + costs.total
        self.cost_input = (self.cost_input or 0.0) + costs.input
        self.cost_output = (self.cost_output or 0.0) + costs.output
        model_totals.rated_inference_calls += 1
        model_totals.cost = (model_totals.cost or 0.0) + costs.total

    def absorb(self, *, other: "UsageAccumulator") -> None:
        """Merge another total into this one (subtree rollup, run total)."""
        self.inference_calls += other.inference_calls
        self.rated_inference_calls += other.rated_inference_calls
        for token_category, nb_tokens in other.nb_tokens_by_category.items():
            self.nb_tokens_by_category[token_category] = self.nb_tokens_by_category.get(token_category, 0) + nb_tokens
        self.total_tokens += other.total_tokens
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost
            self.cost_input = (self.cost_input or 0.0) + (other.cost_input or 0.0)
            self.cost_output = (self.cost_output or 0.0) + (other.cost_output or 0.0)
        for model_key, other_totals in other.by_model.items():
            model_totals = self.by_model.get(model_key)
            if model_totals is None:
                model_totals = _ModelTotals()
                self.by_model[model_key] = model_totals
            model_totals.absorb(other=other_totals)

    def to_node_usage_spec(self, *, subtree: "UsageAccumulator") -> NodeUsageSpec:
        """Pair this node's own total with its subtree total into the wire shape."""
        return NodeUsageSpec(
            inference_calls=self.inference_calls,
            rated_inference_calls=self.rated_inference_calls,
            nb_tokens_by_category=dict(self.nb_tokens_by_category),
            total_tokens=self.total_tokens,
            cost=self.cost,
            cost_input=self.cost_input,
            cost_output=self.cost_output,
            by_model=self._model_specs(),
            subtree_inference_calls=subtree.inference_calls,
            subtree_rated_inference_calls=subtree.rated_inference_calls,
            subtree_nb_tokens_by_category=dict(subtree.nb_tokens_by_category),
            subtree_total_tokens=subtree.total_tokens,
            subtree_cost=subtree.cost,
            subtree_cost_input=subtree.cost_input,
            subtree_cost_output=subtree.cost_output,
            subtree_by_model=subtree._model_specs(),  # noqa: SLF001 — same class, private by convention only
        )

    def _model_specs(self) -> list[ModelUsageSpec]:
        """Per-model breakdown, most-used model first (ties broken by name, for stability)."""
        specs = [
            ModelUsageSpec(
                inference_model_name=name,
                inference_model_id=model_id,
                model_type=model_type,
                inference_calls=totals.inference_calls,
                rated_inference_calls=totals.rated_inference_calls,
                cost=totals.cost,
            )
            for (name, model_id, model_type), totals in self.by_model.items()
        ]
        specs.sort(key=lambda spec: (-spec.inference_calls, spec.inference_model_name, spec.inference_model_id))
        return specs

    def to_self_contained_spec(self) -> NodeUsageSpec:
        """Wire shape for a total that has no subtree distinct from itself.

        Used for ``GraphUsageSpec.total`` and ``GraphUsageSpec.unattributed``, whose
        ``subtree_*`` fields repeat their own by definition.
        """
        return self.to_node_usage_spec(subtree=self)


def roll_up(
    *,
    own_usage_by_node: Mapping[str, UsageAccumulator],
    parent_by_node: Mapping[str, str | None],
) -> dict[str, UsageAccumulator]:
    """Roll each node's own usage up into a per-node subtree total.

    Memoized post-order over the parentage chain: O(nodes), not O(nodes x depth). Two
    malformed-parentage cases are tolerated rather than allowed to blow up, because both
    are reachable from a partial cross-worker event read:

      - a ``parent_node_id`` naming a node absent from ``own_usage_by_node`` — the child
        is treated as a root (it contributes to no subtree but keeps its own total)
        instead of raising ``KeyError``;
      - a cycle in the parentage chain — broken by an in-progress guard and logged, so
        the walk terminates instead of hanging. The rolled-up totals for the nodes on
        the cycle are then incomplete, which is why it is a WARNING and not silent.

    Args:
        own_usage_by_node: Every node in the graph mapped to its own (non-subtree) usage.
        parent_by_node: Every node mapped to its parent node id, or None for a root.

    Returns:
        Every node in ``own_usage_by_node`` mapped to its subtree total.
    """
    children_by_node: dict[str, list[str]] = {}
    for node_id in own_usage_by_node:
        parent_node_id = parent_by_node.get(node_id)
        if parent_node_id is None:
            continue
        if parent_node_id not in own_usage_by_node:
            # Dangling parent: treat this node as a root rather than dropping it.
            continue
        children_by_node.setdefault(parent_node_id, []).append(node_id)

    subtree_by_node: dict[str, UsageAccumulator] = {}
    for start_node_id in own_usage_by_node:
        if start_node_id in subtree_by_node:
            continue
        _walk_subtree(
            start_node_id=start_node_id,
            own_usage_by_node=own_usage_by_node,
            children_by_node=children_by_node,
            subtree_by_node=subtree_by_node,
        )
    return subtree_by_node


def _walk_subtree(
    *,
    start_node_id: str,
    own_usage_by_node: Mapping[str, UsageAccumulator],
    children_by_node: Mapping[str, list[str]],
    subtree_by_node: dict[str, UsageAccumulator],
) -> None:
    """Explicit-stack post-order walk filling ``subtree_by_node`` from ``start_node_id`` down.

    An explicit stack rather than recursion: a deep pipeline must not depend on the
    interpreter's recursion limit.
    """
    in_progress: set[str] = set()
    stack: list[tuple[str, bool]] = [(start_node_id, False)]
    while stack:
        node_id, is_expanded = stack.pop()
        if is_expanded:
            accumulator = UsageAccumulator()
            accumulator.absorb(other=own_usage_by_node[node_id])
            for child_node_id in children_by_node.get(node_id, []):
                child_subtree = subtree_by_node.get(child_node_id)
                if child_subtree is not None:
                    accumulator.absorb(other=child_subtree)
            subtree_by_node[node_id] = accumulator
            in_progress.discard(node_id)
            continue

        if node_id in subtree_by_node:
            continue
        if node_id in in_progress:
            log.warning(f"Cycle in graph node parentage at '{node_id}'; subtree usage rollup will be incomplete")
            continue

        in_progress.add(node_id)
        stack.append((node_id, True))
        for child_node_id in children_by_node.get(node_id, []):
            if child_node_id not in subtree_by_node:
                stack.append((child_node_id, False))


def attribute_usage(
    *,
    own_usage_by_node: Mapping[str, UsageAccumulator],
    parent_by_node: Mapping[str, str | None],
) -> dict[str, NodeUsageSpec]:
    """Turn per-node own usage into per-node wire specs, subtree fields included.

    Every node in ``own_usage_by_node`` gets a spec — zeroed where nothing ran. That is
    ``NodeUsageSpec`` invariant 1: once a run reports any usage at all, no node is left
    reading as "not collected".
    """
    subtree_by_node = roll_up(own_usage_by_node=own_usage_by_node, parent_by_node=parent_by_node)
    return {
        node_id: own_usage.to_node_usage_spec(subtree=subtree_by_node.get(node_id, own_usage)) for node_id, own_usage in own_usage_by_node.items()
    }
