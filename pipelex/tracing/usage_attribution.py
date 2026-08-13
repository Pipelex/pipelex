"""Attribution of inference usage to graph nodes.

One event stream, two projections. ``UsageAggregator`` projects ``UsageReportEvent``
into the flat, client-facing ``tokens_usages`` list (``node_id`` dropped, one record per
call). This module projects the SAME events into per-node groups for the GraphSpec
(``node_id`` kept), and hands each group to ``CostRegistry.aggregate_costs`` — the
shipped cost engine that already produces the run's totals, its per-model grouping and
its per-category token and cost columns.

**No arithmetic lives here.** This module groups usage records by node, walks the
parentage chain to build each node's subtree group, and maps ``AggregatedCosts`` onto
the wire shape. Every number is the cost report's own, so the graph and the cost table
cannot disagree by construction rather than by discipline.

The one thing the engine cannot express is *unrated*: it treats a usage with no rate
table as costing ``0.0``, while the graph must say ``None`` (a dry run and an unpriced
model are not free, they are unpriced). That distinction is a count of the records whose
``unit_costs`` is empty — see ``_rated_count`` — not a reimplementation of costing.
"""

from collections.abc import Mapping, Sequence

from pipelex import log
from pipelex.cogt.llm.llm_report import LLMTokenCostReportField
from pipelex.cogt.usage.cost_registry import AggregatedCosts, CostRegistry
from pipelex.graph.graphspec import ModelUsageSpec, NodeUsageSpec
from pipelex.reporting.reporting_types import AnyTokensUsage

# A node's usage is just the records attributed to it, kept in arrival order.
NodeUsages = list[AnyTokensUsage]


def _rated_count(usages: Sequence[AnyTokensUsage]) -> int:
    """How many of these calls carried a rate table.

    The single fact ``AggregatedCosts`` cannot carry: it prices an unrated call at
    ``0.0``, which is indistinguishable from a genuinely free one. Comparing this to
    ``len(usages)`` is what makes ``cost=None`` (nothing priced) and a partial cost
    (some priced) expressible.
    """
    return sum(1 for tokens_usage in usages if tokens_usage.unit_costs)


def _merge_token_categories(usages: Sequence[AnyTokensUsage]) -> dict[str, int]:
    """Raw provider-reported counts, summed per category, exactly as reported.

    Deliberately the untouched vocabulary rather than the cost report's derived
    ``input_joined`` / ``input_non_cached`` columns: this mirrors the client-facing
    ``TokensUsageRecord.nb_tokens_by_category``, so a consumer sees one token vocabulary
    across the graph and the API.
    """
    merged: dict[str, int] = {}
    for tokens_usage in usages:
        for token_category, nb_tokens in tokens_usage.nb_tokens_by_category.items():
            merged[token_category] = merged.get(token_category, 0) + nb_tokens
    return merged


def _model_specs(*, usages: Sequence[AnyTokensUsage], aggregated: AggregatedCosts) -> list[ModelUsageSpec]:
    """Per-model breakdown, taken from the cost report's own grouping.

    ``AggregatedCosts.grouped_by_model`` already splits tokens and costs per model name;
    all this adds is the model id, the call counts, and the unrated ``None`` the engine
    cannot express. Ordered most-used first (ties by name) so a consumer can read
    ``by_model[0]`` as the dominant model without sorting.
    """
    calls_by_model: dict[str, int] = {}
    rated_by_model: dict[str, int] = {}
    model_ids: dict[str, str] = {}
    for tokens_usage in usages:
        model_name = tokens_usage.inference_model_name
        calls_by_model[model_name] = calls_by_model.get(model_name, 0) + 1
        model_ids.setdefault(model_name, tokens_usage.inference_model_id)
        if tokens_usage.unit_costs:
            rated_by_model[model_name] = rated_by_model.get(model_name, 0) + 1

    specs: list[ModelUsageSpec] = []
    for model_name, model_data in aggregated.grouped_by_model.items():
        rated_calls = rated_by_model.get(model_name, 0)
        model_cost = CostRegistry.compute_total_cost(
            input_non_cached_cost=model_data[LLMTokenCostReportField.COST_INPUT_NON_CACHED],
            input_cached_cost=model_data[LLMTokenCostReportField.COST_INPUT_CACHED],
            output_cost=model_data[LLMTokenCostReportField.COST_OUTPUT],
        )
        specs.append(
            ModelUsageSpec(
                inference_model_name=model_name,
                inference_model_id=model_ids.get(model_name, ""),
                model_type=aggregated.model_types.get(model_name, "llm"),
                inference_calls=calls_by_model.get(model_name, 0),
                rated_inference_calls=rated_calls,
                cost=model_cost if rated_calls else None,
            )
        )
    specs.sort(key=lambda spec: (-spec.inference_calls, spec.inference_model_name, spec.inference_model_id))
    return specs


class _ScopedUsage:
    """One scope's numbers — a node's own, or its whole subtree's.

    Every field is read off ``AggregatedCosts``; the class exists only so the own half
    and the subtree half are computed by identical code.
    """

    def __init__(self, usages: Sequence[AnyTokensUsage]) -> None:
        aggregated = CostRegistry.aggregate_costs(tokens_usages=usages)
        rated_calls = _rated_count(usages)

        self.inference_calls: int = len(usages)
        self.rated_inference_calls: int = rated_calls
        self.nb_tokens_by_category: dict[str, int] = _merge_token_categories(usages)
        self.total_tokens: int = aggregated.total_nb_tokens
        # None, not 0.0, when nothing was priced: unpriced is not free.
        self.cost: float | None = aggregated.total_cost if rated_calls else None
        self.cost_input: float | None = None
        self.cost_output: float | None = None
        if rated_calls:
            records = aggregated.records
            self.cost_input = sum(record.get(LLMTokenCostReportField.COST_INPUT_JOINED, 0.0) for record in records)
            self.cost_output = sum(record.get(LLMTokenCostReportField.COST_OUTPUT, 0.0) for record in records)
        self.by_model: list[ModelUsageSpec] = _model_specs(usages=usages, aggregated=aggregated)


def make_node_usage_spec(*, own_usages: Sequence[AnyTokensUsage], subtree_usages: Sequence[AnyTokensUsage]) -> NodeUsageSpec:
    """Map a node's own usage records and its subtree's onto the wire shape."""
    own = _ScopedUsage(own_usages)
    subtree = _ScopedUsage(subtree_usages)
    return NodeUsageSpec(
        inference_calls=own.inference_calls,
        rated_inference_calls=own.rated_inference_calls,
        nb_tokens_by_category=own.nb_tokens_by_category,
        total_tokens=own.total_tokens,
        cost=own.cost,
        cost_input=own.cost_input,
        cost_output=own.cost_output,
        by_model=own.by_model,
        subtree_inference_calls=subtree.inference_calls,
        subtree_rated_inference_calls=subtree.rated_inference_calls,
        subtree_nb_tokens_by_category=subtree.nb_tokens_by_category,
        subtree_total_tokens=subtree.total_tokens,
        subtree_cost=subtree.cost,
        subtree_cost_input=subtree.cost_input,
        subtree_cost_output=subtree.cost_output,
        subtree_by_model=subtree.by_model,
    )


def make_self_contained_spec(usages: Sequence[AnyTokensUsage]) -> NodeUsageSpec:
    """Wire shape for a total with no subtree distinct from itself.

    Used for ``GraphUsageSpec.total`` and ``GraphUsageSpec.unattributed``, whose
    ``subtree_*`` fields repeat their own by definition.
    """
    return make_node_usage_spec(own_usages=usages, subtree_usages=usages)


def roll_up(
    *,
    own_usages_by_node: Mapping[str, NodeUsages],
    parent_by_node: Mapping[str, str | None],
) -> dict[str, NodeUsages]:
    """Collect each node's own usage records together with every descendant's.

    Memoized post-order over the parentage chain: O(nodes), not O(nodes x depth). Two
    malformed-parentage cases are tolerated rather than allowed to blow up, because both
    are reachable from a partial cross-worker event read:

      - a ``parent_node_id`` naming a node absent from ``own_usages_by_node`` — the child
        is treated as a root (it contributes to no subtree but keeps its own records)
        instead of raising ``KeyError``;
      - a cycle in the parentage chain — broken by an in-progress guard and logged, so
        the walk terminates instead of hanging. The rolled-up records for the nodes on
        the cycle are then incomplete, which is why it is a WARNING and not silent.
    """
    children_by_node: dict[str, list[str]] = {}
    for node_id in own_usages_by_node:
        parent_node_id = parent_by_node.get(node_id)
        if parent_node_id is None:
            continue
        if parent_node_id not in own_usages_by_node:
            # Dangling parent: treat this node as a root rather than dropping it.
            continue
        children_by_node.setdefault(parent_node_id, []).append(node_id)

    subtree_by_node: dict[str, NodeUsages] = {}
    for start_node_id in own_usages_by_node:
        if start_node_id in subtree_by_node:
            continue
        _walk_subtree(
            start_node_id=start_node_id,
            own_usages_by_node=own_usages_by_node,
            children_by_node=children_by_node,
            subtree_by_node=subtree_by_node,
        )
    return subtree_by_node


def _walk_subtree(
    *,
    start_node_id: str,
    own_usages_by_node: Mapping[str, NodeUsages],
    children_by_node: Mapping[str, list[str]],
    subtree_by_node: dict[str, NodeUsages],
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
            collected: NodeUsages = list(own_usages_by_node[node_id])
            for child_node_id in children_by_node.get(node_id, []):
                child_subtree = subtree_by_node.get(child_node_id)
                if child_subtree is not None:
                    collected.extend(child_subtree)
            subtree_by_node[node_id] = collected
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
    own_usages_by_node: Mapping[str, NodeUsages],
    parent_by_node: Mapping[str, str | None],
) -> dict[str, NodeUsageSpec]:
    """Turn per-node usage records into per-node wire specs, subtree fields included.

    Every node in ``own_usages_by_node`` gets a spec — zeroed where nothing ran. That is
    ``NodeUsageSpec`` invariant 1: once a run reports any usage at all, no node is left
    reading as "not collected".
    """
    subtree_by_node = roll_up(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)
    return {
        node_id: make_node_usage_spec(own_usages=own_usages, subtree_usages=subtree_by_node.get(node_id, own_usages))
        for node_id, own_usages in own_usages_by_node.items()
    }
