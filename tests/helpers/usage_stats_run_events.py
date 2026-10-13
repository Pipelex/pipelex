"""Trace events and envelopes for the tests of a run's usage statistics, built the way a run writes them."""

from datetime import UTC, datetime
from typing import Any

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import NodeKind
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsArch, UsageStatsIntegration, UsageStatsOs, UsageStatsSurface
from pipelex.system.usage_stats.usage_stats_events import CommonProperties, UsageStatsEvent, make_envelope
from pipelex.tracing.trace_events import PipeStartEvent, UsageReportEvent

USAGE_STATS_RUN_ID = "run-usage-stats"
USAGE_STATS_INSTALLATION_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def llm_usage_event(
    *,
    model_name: str,
    backend_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    is_rated: bool = True,
    sequence: int = 0,
    model_id: str | None = None,
) -> UsageReportEvent:
    """One inference call's usage, as the backend that served it reports it; an unrated call carries no rate table, so no cost."""
    tokens_usage = LLMTokensUsage(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user_test", pipeline_run_id=USAGE_STATS_RUN_ID),
            pipe_code="secret_pipe_code",
            unit_job_id=UnitJobId.LLM_GEN_TEXT,
            job_category=JobCategory.LLM_JOB,
        ),
        inference_model_name=model_name,
        inference_model_id=model_id or f"{model_name}-provider-id",
        backend_name=backend_name,
        unit_costs={CostCategory.INPUT: 0.003, CostCategory.OUTPUT: 0.015} if is_rated else {},
        nb_tokens_by_category={
            TokenCategory.INPUT: input_tokens,
            TokenCategory.OUTPUT: output_tokens,
            TokenCategory.INPUT_CACHED: cached_tokens,
        },
    )
    return UsageReportEvent(
        pipeline_run_id=USAGE_STATS_RUN_ID,
        workflow_id="direct",
        timestamp=datetime.now(UTC),
        sequence=sequence,
        mode=PipeRunMode.LIVE,
        node_id=f"{USAGE_STATS_RUN_ID}:node_{sequence}",
        tokens_usage=tokens_usage,
    )


def pipe_start_event(*, pipe_type: str, sequence: int) -> PipeStartEvent:
    return PipeStartEvent(
        pipeline_run_id=USAGE_STATS_RUN_ID,
        workflow_id="direct",
        timestamp=datetime.now(UTC),
        sequence=sequence,
        mode=PipeRunMode.LIVE,
        node_id=f"{USAGE_STATS_RUN_ID}:node_{sequence}",
        pipe_code=f"secret_pipe_{sequence}",
        pipe_type=pipe_type,
        node_kind=NodeKind.OPERATOR,
    )


def envelope_of(*, event: UsageStatsEvent) -> dict[str, Any]:
    """The event as a Python program running pipelex would post it."""
    common = CommonProperties(
        tool_version="0.83.0",
        surface=UsageStatsSurface.PYTHON,
        integration=UsageStatsIntegration.PYTHON,
        id_new=False,
        os=UsageStatsOs.LINUX,
        arch=UsageStatsArch.X86_64,
        language_runtime="python-3.13",
        ci=False,
        container=False,
        internal=False,
        notice_version=1,
    )
    return make_envelope(event=event, distinct_id=USAGE_STATS_INSTALLATION_ID, common=common)
