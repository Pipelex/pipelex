"""Unit tests for ReportingManager event emission.

Validates that when an EventLogProtocol is provided, ReportingManager emits
UsageReportEvent alongside existing local accumulation.
"""

from datetime import datetime, timedelta, timezone

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import UsageReportEvent


def _make_test_llm_job(
    pipeline_run_id: str,
    graph_context: GraphContext | None = None,
) -> LLMJob:
    """Create a minimal LLMJob for testing event emission."""
    now = datetime.now(timezone.utc)
    job_metadata = JobMetadata(
        user_id="test_user",
        pipeline_run_id=pipeline_run_id,
        graph_context=graph_context,
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        unit_job_id=UnitJobId.LLM_GEN_TEXT,
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(max_retries=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )


class TestReportingEventEmission:
    """Tests for ReportingManager usage event emission."""

    PIPELINE_RUN_ID = "run_rpt_001"
    WORKFLOW_ID = "wf_rpt_abc"

    def _make_reporting_manager_with_event_log(self) -> tuple[ReportingManager, InMemoryEventLog]:
        """Create a ReportingManager configured with an event log."""
        event_log = InMemoryEventLog()
        manager = ReportingManager()
        manager.setup()
        manager.set_event_log(
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
        )
        manager.open_registry(self.PIPELINE_RUN_ID)
        return manager, event_log

    def test_report_inference_job_emits_usage_event(self) -> None:
        """UsageReportEvent is emitted when reporting an LLM inference job with event_log set."""
        manager, event_log = self._make_reporting_manager_with_event_log()

        llm_job = _make_test_llm_job(self.PIPELINE_RUN_ID)
        manager.report_inference_job(llm_job)

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].tokens_usage.nb_tokens_by_category[TokenCategory.INPUT] == 100
        assert usage_events[0].node_id == "unknown"  # No graph_context parent set

    def test_report_inference_job_captures_node_id_from_graph_context(self) -> None:
        """UsageReportEvent captures the parent node_id from graph context."""
        manager, event_log = self._make_reporting_manager_with_event_log()

        graph_context = GraphContext(
            graph_id="test-graph",
            parent_node_id="test-graph:node_42",
            node_sequence=43,
            data_inclusion=DataInclusionConfig(
                stuff_json_content=False,
                stuff_text_content=False,
                stuff_html_content=False,
                error_stack_traces=False,
            ),
        )

        llm_job = _make_test_llm_job(self.PIPELINE_RUN_ID, graph_context=graph_context)
        manager.report_inference_job(llm_job)

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].node_id == "test-graph:node_42"
        assert usage_events[0].workflow_id == self.WORKFLOW_ID

    def test_no_event_log_works_as_before(self) -> None:
        """ReportingManager without event_log works exactly as before."""
        manager = ReportingManager()
        manager.setup()
        manager.open_registry("direct_run")
        manager.close_registry("direct_run")
        manager.teardown()
