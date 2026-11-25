from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import NodeKind
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.trace_events import PipeEndSuccessEvent, PipeStartEvent, TraceEvent, UsageReportEvent


class IncompleteGraphRun:
    """A run whose trace lost the start events of nodes that still reported inference usage.

    Shared by the report's own tests and by the run boundary's, which apply the run's reporting policy to it.
    """

    PIPELINE_RUN_ID: ClassVar[str] = "run_incomplete"
    REQUEST_ID: ClassVar[str] = "req_incomplete"
    WORKFLOW_ID: ClassVar[str] = "wf_a"
    T0: ClassVar[datetime] = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
    RATES: ClassVar[CostsByCategoryDict] = {CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0}
    # 100 input tokens at $3 per million and 50 output tokens at $15 per million: $0.00105, 1050 millionths of a dollar.
    MICRO_USD_OF_ONE_CALL: ClassVar[int] = 1050
    # What a run's content would leak through if the report quoted it: the pipe, the model, the prompt's owner.
    RUN_CONTENT_MARKERS: ClassVar[tuple[str, ...]] = ("secret_pipe", "secret-model", "user_secret")

    LLM_NODE_ID: ClassVar[str] = f"{PIPELINE_RUN_ID}:{WORKFLOW_ID}:node_llm"
    GHOST_NODE_ID: ClassVar[str] = f"{PIPELINE_RUN_ID}:wf_lost:node_ghost"
    OTHER_GHOST_NODE_ID: ClassVar[str] = f"{PIPELINE_RUN_ID}:wf_lost:node_another"

    @staticmethod
    def base(*, sequence: int, mode: PipeRunMode = PipeRunMode.LIVE) -> dict[str, Any]:
        return {
            "pipeline_run_id": IncompleteGraphRun.PIPELINE_RUN_ID,
            "workflow_id": IncompleteGraphRun.WORKFLOW_ID,
            "attempt": 1,
            "lineage": [],
            "path": None,
            "timestamp": IncompleteGraphRun.T0 + timedelta(seconds=sequence),
            "sequence": sequence,
            "mode": mode,
        }

    @staticmethod
    def usage_event(*, sequence: int, node_id: str, mode: PipeRunMode = PipeRunMode.LIVE) -> UsageReportEvent:
        usage = LLMTokensUsage(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(
                    storage_scope="test/scope", read_scope=None, user_id="user_secret", pipeline_run_id=IncompleteGraphRun.PIPELINE_RUN_ID
                ),
                pipe_code="secret_pipe",
                unit_job_id=UnitJobId.LLM_GEN_TEXT,
                job_category=JobCategory.LLM_JOB,
            ),
            inference_model_name="secret-model",
            inference_model_id="secret-model-id",
            unit_costs=IncompleteGraphRun.RATES,
            nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        )
        return UsageReportEvent(**IncompleteGraphRun.base(sequence=sequence, mode=mode), node_id=node_id, tokens_usage=usage)

    @staticmethod
    def one_node_run(*, mode: PipeRunMode = PipeRunMode.LIVE) -> list[TraceEvent]:
        """A run of one LLM node that started, ran one call and ended."""
        node_id = IncompleteGraphRun.LLM_NODE_ID
        return [
            PipeStartEvent(
                pipe_ref=None,
                **IncompleteGraphRun.base(sequence=0, mode=mode),
                node_id=node_id,
                parent_node_id=None,
                pipe_code="secret_pipe",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            IncompleteGraphRun.usage_event(sequence=1, node_id=node_id, mode=mode),
            PipeEndSuccessEvent(
                pipe_code="secret_pipe",
                pipe_ref=None,
                pipe_type="PipeLLM",
                **IncompleteGraphRun.base(sequence=2, mode=mode),
                node_id=node_id,
                ended_at=IncompleteGraphRun.T0 + timedelta(seconds=2),
            ),
        ]

    @staticmethod
    def run_with_lost_starts(*, mode: PipeRunMode = PipeRunMode.LIVE) -> list[TraceEvent]:
        """The run, plus two calls made by a node whose start event was lost and one by another such node."""
        return [
            *IncompleteGraphRun.one_node_run(mode=mode),
            IncompleteGraphRun.usage_event(sequence=3, node_id=IncompleteGraphRun.GHOST_NODE_ID, mode=mode),
            IncompleteGraphRun.usage_event(sequence=4, node_id=IncompleteGraphRun.GHOST_NODE_ID, mode=mode),
            IncompleteGraphRun.usage_event(sequence=5, node_id=IncompleteGraphRun.OTHER_GHOST_NODE_ID, mode=mode),
        ]
