"""A run calling both kinds of one handle reports two models, never one merged row.

A handle names one model per model type, so `gpt-6-luna` may be called as an LLM and as a judgment model
in one run. The cost table, the agent summary and the graph's usage attribution all group by the model
type and the name together: grouping by the name alone would merge the two kinds into one row and type
it by whichever call came last.
"""

from pipelex.cogt.judgment.judgment_report import JudgmentTokensUsage
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_registry import CostRegistry, ModelUsageKey
from pipelex.graph.graphspec import ModelUsageSpec
from pipelex.system.job_metadata import JobCategory, JobMetadata, UnitJobId
from pipelex.tracing.usage_attribution import make_self_contained_spec
from tests.unit.pipelex.cogt.usage.test_data import RATED_NB_TOKENS, RATED_UNIT_COSTS, UsageFixtures

TWIN_HANDLE = "gpt-6-luna"


def _twin_usages() -> list[LLMTokensUsage | JudgmentTokensUsage]:
    llm_job_metadata: JobMetadata = UsageFixtures.full_job_metadata(unit_job_id=UnitJobId.LLM_GEN_TEXT, job_category=JobCategory.LLM_JOB)
    judgment_job_metadata: JobMetadata = UsageFixtures.full_job_metadata(unit_job_id=UnitJobId.JUDGMENT_ANSWER, job_category=JobCategory.JUDGMENT_JOB)
    return [
        LLMTokensUsage(
            job_metadata=llm_job_metadata,
            inference_model_name=TWIN_HANDLE,
            inference_model_id="gpt-6-luna-llm",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        ),
        LLMTokensUsage(
            job_metadata=llm_job_metadata,
            inference_model_name=TWIN_HANDLE,
            inference_model_id="gpt-6-luna-llm",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        ),
        JudgmentTokensUsage(
            job_metadata=judgment_job_metadata,
            inference_model_name=TWIN_HANDLE,
            inference_model_id="gpt-6-luna-decisions",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        ),
    ]


class TestUsagePerModelPair:
    def test_the_aggregation_keeps_one_group_per_kind(self) -> None:
        aggregated = CostRegistry.aggregate_costs(tokens_usages=_twin_usages())

        assert set(aggregated.grouped_by_model) == {
            ModelUsageKey(model_type="llm", model_name=TWIN_HANDLE),
            ModelUsageKey(model_type="judgment", model_name=TWIN_HANDLE),
        }

    def test_the_cost_summary_reports_two_rows(self) -> None:
        summary = CostRegistry.build_cost_summary(_twin_usages())

        assert summary is not None
        rows = sorted((row["model"], row["model_type"]) for row in summary["by_model"])
        assert rows == [(TWIN_HANDLE, "judgment"), (TWIN_HANDLE, "llm")]
        llm_row = next(row for row in summary["by_model"] if row["model_type"] == "llm")
        judgment_row = next(row for row in summary["by_model"] if row["model_type"] == "judgment")
        assert llm_row["cost"] == 2 * judgment_row["cost"]

    def test_the_usage_attribution_reports_two_entries(self) -> None:
        by_model = make_self_contained_spec(_twin_usages()).by_model

        assert [(spec.inference_model_name, spec.model_type, spec.inference_calls, spec.inference_model_id) for spec in by_model] == [
            (TWIN_HANDLE, "llm", 2, "gpt-6-luna-llm"),
            (TWIN_HANDLE, "judgment", 1, "gpt-6-luna-decisions"),
        ]
        assert all(isinstance(spec, ModelUsageSpec) for spec in by_model)

    def test_entries_of_one_name_and_one_call_count_are_ordered_by_type(self) -> None:
        """The sort breaks a tie on the name with the type, so the order never depends on the order of the calls."""
        usages = _twin_usages()
        one_call_each = [usages[0], usages[2]]

        forward = [spec.model_type for spec in make_self_contained_spec(one_call_each).by_model]
        backward = [spec.model_type for spec in make_self_contained_spec(list(reversed(one_call_each))).by_model]

        assert forward == backward == ["judgment", "llm"]

    def test_the_cost_summary_is_the_same_in_either_arrival_order(self) -> None:
        """Grouped by the name alone, the merged row took the type of whichever call came last."""
        usages = _twin_usages()
        judgment_last = CostRegistry.build_cost_summary(usages)
        judgment_first = CostRegistry.build_cost_summary([usages[2], usages[0], usages[1]])

        assert judgment_last is not None
        assert judgment_first is not None
        by_type_last = {row["model_type"]: row for row in judgment_last["by_model"]}
        by_type_first = {row["model_type"]: row for row in judgment_first["by_model"]}
        assert by_type_last == by_type_first
        assert set(by_type_last) == {"llm", "judgment"}
