import pytest

from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.cost_registry import CostRegistry, compute_tokens_usage_cost
from pipelex.reporting.reporting_types import AnyTokensUsage
from tests.unit.pipelex.cogt.usage.test_data import RATED_EXPECTED_COST, UsageFixtures


class TestComputeTokensUsageCost:
    def test_none_when_unrated(self):
        """No rate table (own-GPU, dry/mock run) means no cost claim — None, not 0.0."""
        assert compute_tokens_usage_cost(UsageFixtures.unrated_usage()) is None

    def test_rated_cost_value(self):
        assert compute_tokens_usage_cost(UsageFixtures.llm_usage()) == RATED_EXPECTED_COST

    def test_cached_discount_fallback(self):
        """Without an explicit cached rate, cached input tokens cost 50% of the input rate."""
        expected = 600 * (2.0 / 1_000_000) + 400 * (0.5 * 2.0 / 1_000_000) + 250 * (10.0 / 1_000_000)
        assert compute_tokens_usage_cost(UsageFixtures.cached_fallback_usage()) == expected

    @pytest.mark.parametrize(
        "tokens_usage",
        UsageFixtures.all_variants(),
        ids=["llm", "img_gen", "extract", "search"],
    )
    def test_parity_with_cost_registry_per_record(self, tokens_usage: AnyTokensUsage):
        """The wire cost equals the canonical CostRegistry total for the same record — one cost engine, no drift."""
        cost_report = CostRegistry.complete_cost_report(tokens_usage=tokens_usage)
        registry_total = CostRegistry.compute_total_cost(
            input_non_cached_cost=cost_report.costs_by_token_category[CostCategory.INPUT_NON_CACHED],
            input_cached_cost=cost_report.costs_by_token_category[CostCategory.INPUT_CACHED],
            output_cost=cost_report.costs_by_token_category.get(CostCategory.OUTPUT, 0.0),
        )
        assert compute_tokens_usage_cost(tokens_usage) == registry_total

    def test_parity_with_aggregate_run_total(self):
        """Summing per-record wire costs reproduces the CLI cost table's run total."""
        tokens_usages = UsageFixtures.all_variants()
        wire_total = 0.0
        for tokens_usage in tokens_usages:
            record_cost = compute_tokens_usage_cost(tokens_usage)
            assert record_cost is not None
            wire_total += record_cost
        aggregated = CostRegistry.aggregate_costs(tokens_usages=tokens_usages)
        assert wire_total == aggregated.total_cost
