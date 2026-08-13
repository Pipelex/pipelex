"""Tests for per-node usage attribution: the wire mapping and the subtree rollup."""

import math

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.graph.graphspec import NodeUsageSpec
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.system.job_metadata import JobCategory, JobMetadata, UnitJobId
from pipelex.tracing.usage_attribution import attribute_usage, make_node_usage_spec, roll_up

# Per-million-token USD, so 100 input + 50 output tokens cost 0.0003 + 0.00075.
_RATES: CostsByCategoryDict = {CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0}
_UNRATED: CostsByCategoryDict = {}
_COST_OF_ONE_RATED_CALL = 100 * 3.0 / 1_000_000 + 50 * 15.0 / 1_000_000


def _is_close(actual: float | None, *, expected: float) -> bool:
    """Cost comparison that also pins down "not None" — a None cost is never "close"."""
    return actual is not None and math.isclose(actual, expected, rel_tol=1e-9)


def _make_usage(
    *,
    unit_costs: CostsByCategoryDict,
    nb_tokens_by_category: NbTokensByCategoryDict | None = None,
    model_name: str = "test-model",
) -> AnyTokensUsage:
    return LLMTokensUsage(
        job_metadata=JobMetadata(
            user_id="user_test",
            pipeline_run_id="run_001",
            pipe_code="test_pipe",
            unit_job_id=UnitJobId.LLM_GEN_TEXT,
            job_category=JobCategory.LLM_JOB,
        ),
        inference_model_name=model_name,
        inference_model_id=f"{model_name}-id",
        unit_costs=unit_costs,
        nb_tokens_by_category=nb_tokens_by_category or {TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )


def _usages_with(*, unit_costs_per_call: list[CostsByCategoryDict]) -> list[AnyTokensUsage]:
    return [_make_usage(unit_costs=unit_costs) for unit_costs in unit_costs_per_call]


def _leaf_spec(*, unit_costs_per_call: list[CostsByCategoryDict]) -> NodeUsageSpec:
    """The wire spec for a leaf node making these calls — a leaf's subtree is itself."""
    usages = _usages_with(unit_costs_per_call=unit_costs_per_call)
    return make_node_usage_spec(own_usages=usages, subtree_usages=usages)


class TestUsageAttribution:
    """Tests for make_node_usage_spec(), roll_up() and attribute_usage()."""

    def test_one_rated_call(self) -> None:
        """Counts, tokens and cost all land, and come from the shipped cost engine."""
        spec = _leaf_spec(unit_costs_per_call=[_RATES])

        assert spec.inference_calls == 1
        assert spec.rated_inference_calls == 1
        assert spec.nb_tokens_by_category == {TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50}
        assert spec.total_tokens == 150
        assert _is_close(spec.cost, expected=_COST_OF_ONE_RATED_CALL)

    def test_several_calls_on_one_node_add_up(self) -> None:
        """Two calls on one node add up, per category and in total."""
        spec = _leaf_spec(unit_costs_per_call=[_RATES, _RATES])

        assert spec.inference_calls == 2
        assert spec.nb_tokens_by_category == {TokenCategory.INPUT: 200, TokenCategory.OUTPUT: 100}
        assert spec.total_tokens == 300
        assert _is_close(spec.cost, expected=2 * _COST_OF_ONE_RATED_CALL)

    def test_invariant_2_unrated_keeps_cost_none(self) -> None:
        """A call with no rate table counts as a call, and cost stays None — never 0.0.

        This is the one thing ``AggregatedCosts`` cannot express: it prices an unrated
        call at 0.0, which would render as "free" rather than "unpriced".
        """
        spec = _leaf_spec(unit_costs_per_call=[_UNRATED, _UNRATED])

        assert spec.inference_calls == 2
        assert spec.rated_inference_calls == 0
        assert spec.cost is None
        assert spec.total_tokens == 300

    def test_invariant_2_no_call_is_distinguishable_from_only_unrated_calls(self) -> None:
        """Both have cost None; inference_calls is what tells them apart."""
        ran_nothing = _leaf_spec(unit_costs_per_call=[])
        only_unrated = _leaf_spec(unit_costs_per_call=[_UNRATED])

        assert ran_nothing.cost is None
        assert only_unrated.cost is None
        assert ran_nothing.inference_calls == 0
        assert only_unrated.inference_calls == 1

    def test_invariant_3_mixed_rated_and_unrated_is_a_lower_bound(self) -> None:
        """Cost covers only the rated calls, and rated < calls says so."""
        spec = _leaf_spec(unit_costs_per_call=[_RATES, _UNRATED])

        assert spec.inference_calls == 2
        assert spec.rated_inference_calls == 1
        assert _is_close(spec.cost, expected=_COST_OF_ONE_RATED_CALL)

    def test_invariant_4_total_tokens_is_not_the_sum_of_the_categories(self) -> None:
        """input_cached is a subset of input, so summing the dict double-counts it."""
        usages = [
            _make_usage(
                unit_costs=_RATES,
                nb_tokens_by_category={
                    TokenCategory.INPUT: 100,
                    TokenCategory.INPUT_CACHED: 40,
                    TokenCategory.OUTPUT: 50,
                },
            )
        ]
        spec = make_node_usage_spec(own_usages=usages, subtree_usages=usages)

        assert spec.total_tokens == 150
        assert sum(spec.nb_tokens_by_category.values()) == 190

    def test_invariant_5_input_and_output_costs_split_the_total(self) -> None:
        """cost_input + cost_output == cost: one number by direction, not extra charges."""
        spec = _leaf_spec(unit_costs_per_call=[_RATES, _RATES])

        assert _is_close(spec.cost_input, expected=2 * 100 * 3.0 / 1_000_000)
        assert _is_close(spec.cost_output, expected=2 * 50 * 15.0 / 1_000_000)
        assert spec.cost_input is not None
        assert spec.cost_output is not None
        assert _is_close(spec.cost_input + spec.cost_output, expected=spec.cost or 0.0)

    def test_component_costs_are_none_on_exactly_the_same_condition_as_cost(self) -> None:
        """Invariant 2 covers the components too — unrated has no input or output price."""
        for spec in (_leaf_spec(unit_costs_per_call=[_UNRATED]), _leaf_spec(unit_costs_per_call=[])):
            assert spec.cost is None
            assert spec.cost_input is None
            assert spec.cost_output is None

    def test_by_model_keeps_the_two_models_of_one_node_apart(self) -> None:
        """A PipeLLM's text pass and object pass resolve separately — both must survive."""
        usages = [
            _make_usage(unit_costs=_RATES, model_name="sonnet"),
            _make_usage(unit_costs=_RATES, model_name="sonnet"),
            _make_usage(unit_costs=_RATES, model_name="structurer"),
        ]
        spec = make_node_usage_spec(own_usages=usages, subtree_usages=usages)

        assert [entry.inference_model_name for entry in spec.by_model] == ["sonnet", "structurer"]
        assert [entry.inference_calls for entry in spec.by_model] == [2, 1]
        assert [entry.inference_model_id for entry in spec.by_model] == ["sonnet-id", "structurer-id"]
        # The per-model calls account for every call the node made.
        assert sum(entry.inference_calls for entry in spec.by_model) == spec.inference_calls

    def test_by_model_is_ordered_by_calls_then_name(self) -> None:
        """Most-used model first, so a consumer can take the first entry as dominant."""
        usages = [_make_usage(unit_costs=_RATES, model_name=name) for name in ["alpha", "beta", "beta", "gamma", "gamma", "gamma"]]
        spec = make_node_usage_spec(own_usages=usages, subtree_usages=usages)

        assert [entry.inference_model_name for entry in spec.by_model] == ["gamma", "beta", "alpha"]

    def test_by_model_cost_is_none_for_an_unrated_model(self) -> None:
        """Invariant 2 holds per model: a model with no rate table reports no price."""
        usages = [
            _make_usage(unit_costs=_RATES, model_name="priced"),
            _make_usage(unit_costs=_UNRATED, model_name="own-gpu"),
        ]
        spec = make_node_usage_spec(own_usages=usages, subtree_usages=usages)
        by_name = {entry.inference_model_name: entry for entry in spec.by_model}

        assert _is_close(by_name["priced"].cost, expected=_COST_OF_ONE_RATED_CALL)
        assert by_name["priced"].rated_inference_calls == 1
        assert by_name["own-gpu"].cost is None
        assert by_name["own-gpu"].rated_inference_calls == 0
        assert by_name["own-gpu"].inference_calls == 1

    def test_by_model_carries_the_model_type_discriminator(self) -> None:
        """model_type is what tells a consumer whether that model's tokens are real."""
        spec = _leaf_spec(unit_costs_per_call=[_RATES])

        assert spec.by_model[0].model_type == "llm"

    def test_leaf_subtree_equals_own(self) -> None:
        """A childless node's subtree is exactly itself."""
        own_usages_by_node = {"leaf": _usages_with(unit_costs_per_call=[_RATES])}

        spec = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node={"leaf": None})["leaf"]

        assert spec.subtree_inference_calls == 1
        assert spec.subtree_total_tokens == 150
        assert _is_close(spec.subtree_cost, expected=_COST_OF_ONE_RATED_CALL)

    def test_controller_subtree_sums_its_children(self) -> None:
        """A controller runs no inference of its own but reports its children's."""
        own_usages_by_node: dict[str, list[AnyTokensUsage]] = {
            "ctrl": [],
            "llm_a": _usages_with(unit_costs_per_call=[_RATES]),
            "llm_b": _usages_with(unit_costs_per_call=[_RATES]),
            "func_c": [],
        }
        parent_by_node: dict[str, str | None] = {"ctrl": None, "llm_a": "ctrl", "llm_b": "ctrl", "func_c": "ctrl"}

        usage_specs = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)

        controller_spec = usage_specs["ctrl"]
        assert controller_spec.inference_calls == 0
        assert controller_spec.cost is None
        assert controller_spec.subtree_inference_calls == 2
        assert controller_spec.subtree_total_tokens == 300
        assert _is_close(controller_spec.subtree_cost, expected=2 * _COST_OF_ONE_RATED_CALL)
        assert usage_specs["func_c"].subtree_inference_calls == 0
        assert usage_specs["func_c"].subtree_cost is None

    def test_nested_three_deep_counts_each_call_once(self) -> None:
        """Every ancestor sees the whole subtree below it, once each."""
        own_usages_by_node: dict[str, list[AnyTokensUsage]] = {
            "root": [],
            "mid": _usages_with(unit_costs_per_call=[_RATES]),
            "leaf_a": _usages_with(unit_costs_per_call=[_RATES]),
            "leaf_b": _usages_with(unit_costs_per_call=[_RATES]),
        }
        parent_by_node: dict[str, str | None] = {"root": None, "mid": "root", "leaf_a": "mid", "leaf_b": "mid"}

        usage_specs = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)

        assert usage_specs["leaf_a"].subtree_inference_calls == 1
        assert usage_specs["mid"].subtree_inference_calls == 3
        assert usage_specs["root"].subtree_inference_calls == 3
        assert _is_close(usage_specs["root"].subtree_cost, expected=3 * _COST_OF_ONE_RATED_CALL)

    def test_all_unrated_subtree_keeps_subtree_cost_none(self) -> None:
        """An entirely unrated subtree must not roll up into a $0.00 controller."""
        own_usages_by_node: dict[str, list[AnyTokensUsage]] = {
            "ctrl": [],
            "llm_a": _usages_with(unit_costs_per_call=[_UNRATED]),
        }
        parent_by_node: dict[str, str | None] = {"ctrl": None, "llm_a": "ctrl"}

        controller_spec = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)["ctrl"]

        assert controller_spec.subtree_cost is None
        assert controller_spec.subtree_inference_calls == 1
        assert controller_spec.subtree_total_tokens == 150

    def test_subtree_by_model_merges_the_models_of_a_whole_branch(self) -> None:
        """A controller reports every model its branch used, merged across children."""
        own_usages_by_node: dict[str, list[AnyTokensUsage]] = {
            "ctrl": [],
            "left": [_make_usage(unit_costs=_RATES, model_name="sonnet")],
            "right": [
                _make_usage(unit_costs=_RATES, model_name="sonnet"),
                _make_usage(unit_costs=_RATES, model_name="haiku"),
            ],
        }
        parent_by_node: dict[str, str | None] = {"ctrl": None, "left": "ctrl", "right": "ctrl"}

        controller_spec = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)["ctrl"]

        assert controller_spec.by_model == []
        by_name = {entry.inference_model_name: entry for entry in controller_spec.subtree_by_model}
        assert by_name["sonnet"].inference_calls == 2
        assert by_name["haiku"].inference_calls == 1
        assert _is_close(by_name["sonnet"].cost, expected=2 * _COST_OF_ONE_RATED_CALL)

    def test_component_costs_roll_up_through_a_subtree(self) -> None:
        """A controller's branch cost splits by direction the same way a leaf's does."""
        own_usages_by_node: dict[str, list[AnyTokensUsage]] = {
            "ctrl": [],
            "llm_a": _usages_with(unit_costs_per_call=[_RATES]),
            "llm_b": _usages_with(unit_costs_per_call=[_RATES]),
        }
        parent_by_node: dict[str, str | None] = {"ctrl": None, "llm_a": "ctrl", "llm_b": "ctrl"}

        controller_spec = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)["ctrl"]

        assert controller_spec.cost_input is None
        assert controller_spec.subtree_cost_input is not None
        assert controller_spec.subtree_cost_output is not None
        assert _is_close(
            controller_spec.subtree_cost_input + controller_spec.subtree_cost_output,
            expected=controller_spec.subtree_cost or 0.0,
        )

    def test_roll_up_survives_a_cycle_in_the_parent_chain(self) -> None:
        """A parentage cycle must terminate, not hang, and still produce every node."""
        own_usages_by_node = {
            "node_a": _usages_with(unit_costs_per_call=[_RATES]),
            "node_b": _usages_with(unit_costs_per_call=[_RATES]),
        }
        parent_by_node: dict[str, str | None] = {"node_a": "node_b", "node_b": "node_a"}

        subtree_by_node = roll_up(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)

        assert set(subtree_by_node.keys()) == {"node_a", "node_b"}
        for usages in subtree_by_node.values():
            assert len(usages) >= 1

    def test_roll_up_treats_a_dangling_parent_as_a_root(self) -> None:
        """A parent absent from the node set must not raise, and must not lose the child."""
        own_usages_by_node = {
            "orphan": _usages_with(unit_costs_per_call=[_RATES]),
            "other": _usages_with(unit_costs_per_call=[_RATES]),
        }
        parent_by_node: dict[str, str | None] = {"orphan": "node_from_another_worker", "other": None}

        usage_specs = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)

        assert usage_specs["orphan"].subtree_inference_calls == 1
        assert _is_close(usage_specs["orphan"].subtree_cost, expected=_COST_OF_ONE_RATED_CALL)
        assert usage_specs["other"].subtree_inference_calls == 1

    def test_attribute_usage_gives_every_node_a_spec(self) -> None:
        """Invariant 1: a node that ran no inference is zeroed, never left specless."""
        own_usages_by_node: dict[str, list[AnyTokensUsage]] = {
            "ctrl": [],
            "llm_a": _usages_with(unit_costs_per_call=[_RATES]),
        }
        parent_by_node: dict[str, str | None] = {"ctrl": None, "llm_a": "ctrl"}

        usage_specs = attribute_usage(own_usages_by_node=own_usages_by_node, parent_by_node=parent_by_node)

        assert set(usage_specs.keys()) == {"ctrl", "llm_a"}
        assert usage_specs["llm_a"].inference_calls == 1
        assert usage_specs["ctrl"].inference_calls == 0
