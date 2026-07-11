"""Aggregation + costing of NON-LLM token usage (img-gen / extract / search).

Every usage test in the tree uses ``LLMTokensUsage`` only — img-gen, extract,
and search usage is never routed through the aggregator + cost registry, and
never round-tripped through the ``UsageReportEvent`` discriminated union that
carries it across worker processes. This module pins all three:

1. each non-LLM usage survives a ``UsageReportEvent`` JSON round-trip with its
   ``model_type`` discriminator intact (the cross-process serialization concern),
2. ``UsageAggregator.aggregate`` surfaces them, and
3. ``CostRegistry.aggregate_costs`` prices them into the run totals.
"""

from datetime import UTC, datetime

from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.search.search_report import SearchTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.tracing.trace_events import UsageReportEvent
from pipelex.tracing.usage_aggregator import UsageAggregator


def _job_metadata() -> JobMetadata:
    return JobMetadata(user_id="test-user", pipeline_run_id="run-non-llm")


def _usage_event(tokens_usage: AnyTokensUsage, sequence: int) -> UsageReportEvent:
    return UsageReportEvent(
        pipeline_run_id="run-non-llm",
        workflow_id="wf-non-llm",
        writer_id="act_test",
        timestamp=datetime.now(UTC),
        sequence=sequence,
        node_id=f"g:node_{sequence}",
        tokens_usage=tokens_usage,
    )


class TestNonLLMUsageAggregation:
    """Img-gen, extract, and search usage aggregate and cost like LLM usage does."""

    def test_non_llm_usage_round_trips_aggregates_and_costs(self) -> None:
        img_gen_usage = ImgGenTokensUsage(
            job_metadata=_job_metadata(),
            inference_model_name="img-gen-model",
            inference_model_id="img-gen-model-id",
            unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 2000},
            nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 200},
        )
        extract_usage = ExtractTokensUsage(
            job_metadata=_job_metadata(),
            inference_model_name="extract-model",
            inference_model_id="extract-model-id",
            unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 1000},
            nb_tokens_by_category={TokenCategory.INPUT: 300, TokenCategory.OUTPUT: 400},
        )
        search_usage = SearchTokensUsage(
            job_metadata=_job_metadata(),
            inference_model_name="search-model",
            inference_model_id="search-model-id",
            unit_costs={CostCategory.INPUT: 5000, CostCategory.OUTPUT: 5000},
            nb_tokens_by_category={TokenCategory.INPUT: 10, TokenCategory.OUTPUT: 20},
        )

        raw_events = [
            _usage_event(img_gen_usage, sequence=0),
            _usage_event(extract_usage, sequence=1),
            _usage_event(search_usage, sequence=2),
        ]
        # Round-trip each event through JSON, exactly as the runner fallback persists it and the
        # assembler reads it back. This proves the AnyTokensUsage discriminated union restores the
        # right concrete non-LLM type (a NamedTuple/dataclass would silently corrupt across the wire).
        events = [UsageReportEvent.model_validate_json(event.model_dump_json()) for event in raw_events]

        tokens_usages = UsageAggregator.aggregate(events)
        assert [usage.model_type for usage in tokens_usages] == ["img_gen", "extract", "search"]
        assert isinstance(tokens_usages[0], ImgGenTokensUsage)
        assert isinstance(tokens_usages[1], ExtractTokensUsage)
        assert isinstance(tokens_usages[2], SearchTokensUsage)

        aggregated = CostRegistry.aggregate_costs(tokens_usages=tokens_usages)

        # total_nb_tokens = sum(input_joined) + sum(output) = (100+300+10) + (200+400+20)
        assert aggregated.total_nb_tokens == 1030
        # per-usage cost (no cached tokens): input*unit_in/1e6 + output*unit_out/1e6
        #   img-gen: 100*0.001 + 200*0.002 = 0.5
        #   extract: 300*0.001 + 400*0.001 = 0.7
        #   search:  10*0.005  + 20*0.005  = 0.15
        assert abs(aggregated.total_cost - 1.35) < 1e-9
        assert aggregated.has_reportable_usage is True
        assert set(aggregated.grouped_by_model.keys()) == {"img-gen-model", "extract-model", "search-model"}
        assert aggregated.model_types == {
            "img-gen-model": "img_gen",
            "extract-model": "extract",
            "search-model": "search",
        }
