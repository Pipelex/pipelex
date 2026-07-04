"""Trace event models for distributed pipeline tracing.

Defines serializable event types that capture the same information as
GraphTracer's in-memory accumulation, but as immutable records suitable
for NDJSON file storage and cross-worker graph assembly.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from pipelex.graph.graphspec import EdgeKind, ErrorSpec, IOSpec, NodeKind
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import StrEnum


class TraceEventKind(StrEnum):
    """Discriminator for trace event types."""

    PIPE_START = "pipe_start"
    PIPE_END_SUCCESS = "pipe_end_success"
    PIPE_END_ERROR = "pipe_end_error"
    PIPE_END_SKIPPED = "pipe_end_skipped"
    EDGE = "edge"
    CONTROLLER_OUTPUT = "controller_output"
    BATCH_ITEM = "batch_item"
    BATCH_AGGREGATE = "batch_aggregate"
    PARALLEL_COMBINE = "parallel_combine"
    EXECUTION_DATA = "execution_data"
    USAGE_REPORT = "usage_report"


class TraceEvent(BaseModel):
    """Base model for all trace events.

    Shared fields:
    - pipeline_run_id: identifies the pipeline execution
    - workflow_id: Temporal workflow ID or "direct" for in-process mode
    - writer_id: identifies the emitting event-log instance, so two writers
        sharing the same (pipeline_run_id, workflow_id) partition can emit
        independent sequence streams without colliding. Defaults to "primary",
        which preserves the legacy single-writer NDJSON file naming and DDB
        sort-key shape; non-default values come from the per-process activity
        event log used by separate-process workers.
    - event_kind: discriminator for the event subclass (defined on each subclass as Literal)
    - timestamp: UTC, for display/debugging only
    - sequence: per-writer monotonic counter, for ordering and deduplication
    """

    pipeline_run_id: str
    workflow_id: str
    writer_id: str = "primary"
    timestamp: datetime
    sequence: int


# ---------------------------------------------------------------------------
# Event subclasses
# ---------------------------------------------------------------------------


class PipeStartEvent(TraceEvent):
    """Emitted when a pipe begins execution."""

    event_kind: Literal[TraceEventKind.PIPE_START] = TraceEventKind.PIPE_START
    node_id: str
    parent_node_id: str | None = None
    pipe_code: str
    pipe_type: str
    node_kind: NodeKind
    description: str | None = None
    domain_code: str | None = None
    input_specs: list[IOSpec] = Field(default_factory=empty_list_factory_of(IOSpec))
    pipe_data: dict[str, Any] = Field(default_factory=dict)
    concept_data: list[dict[str, Any]] = Field(default_factory=empty_list_factory_of(dict))


class PipeEndSuccessEvent(TraceEvent):
    """Emitted when a pipe completes successfully."""

    event_kind: Literal[TraceEventKind.PIPE_END_SUCCESS] = TraceEventKind.PIPE_END_SUCCESS
    node_id: str
    ended_at: datetime
    output_spec: IOSpec | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    output_concept_data: dict[str, Any] = Field(default_factory=dict)


class PipeEndErrorEvent(TraceEvent):
    """Emitted when a pipe fails."""

    event_kind: Literal[TraceEventKind.PIPE_END_ERROR] = TraceEventKind.PIPE_END_ERROR
    node_id: str
    ended_at: datetime
    error: ErrorSpec


class PipeEndSkippedEvent(TraceEvent):
    """Emitted when a pipe is lifted (skipped) because a plain input resolved absent (D3).

    A skip is a successful outcome — the run continues and the pipe's output is a recorded
    absence — but it gets its own node state so graph consumers can render it distinctly.
    """

    event_kind: Literal[TraceEventKind.PIPE_END_SKIPPED] = TraceEventKind.PIPE_END_SKIPPED
    node_id: str
    ended_at: datetime
    skip_reason: str


class EdgeEvent(TraceEvent):
    """Emitted when an edge is added (CONTAINS, SELECTED_OUTCOME, etc.)."""

    event_kind: Literal[TraceEventKind.EDGE] = TraceEventKind.EDGE
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_kind: EdgeKind
    optional: bool = False
    label: str | None = None
    source_stuff_digest: str | None = None
    target_stuff_digest: str | None = None


class ControllerOutputEvent(TraceEvent):
    """Emitted when a controller registers an additional output."""

    event_kind: Literal[TraceEventKind.CONTROLLER_OUTPUT] = TraceEventKind.CONTROLLER_OUTPUT
    node_id: str
    output_spec: IOSpec


class BatchItemEvent(TraceEvent):
    """Emitted when a batch item extraction is registered."""

    event_kind: Literal[TraceEventKind.BATCH_ITEM] = TraceEventKind.BATCH_ITEM
    list_stuff_code: str
    item_stuff_code: str
    item_index: int
    batch_controller_node_id: str


class BatchAggregateEvent(TraceEvent):
    """Emitted when a batch aggregation is registered."""

    event_kind: Literal[TraceEventKind.BATCH_AGGREGATE] = TraceEventKind.BATCH_AGGREGATE
    output_list_stuff_code: str
    item_stuff_code: str
    item_index: int
    batch_controller_node_id: str


class ParallelCombineEvent(TraceEvent):
    """Emitted when a parallel combine is registered.

    branch_producer_node_ids contains (branch_stuff_code, producer_node_id) pairs
    snapshotted from _stuff_producer_map before register_controller_output overrides it.
    """

    event_kind: Literal[TraceEventKind.PARALLEL_COMBINE] = TraceEventKind.PARALLEL_COMBINE
    combined_stuff_code: str
    branch_stuff_codes: list[str]
    parallel_controller_node_id: str
    branch_producer_node_ids: list[tuple[str, str]]


class ExecutionDataEvent(TraceEvent):
    """Emitted when a pipe registers execution metadata (rendered prompts, resolved models, etc.)."""

    event_kind: Literal[TraceEventKind.EXECUTION_DATA] = TraceEventKind.EXECUTION_DATA
    node_id: str
    execution_data: dict[str, Any] = Field(default_factory=dict)


class UsageReportEvent(TraceEvent):
    """Emitted when an inference job reports token usage."""

    event_kind: Literal[TraceEventKind.USAGE_REPORT] = TraceEventKind.USAGE_REPORT
    node_id: str
    tokens_usage: AnyTokensUsage


# ---------------------------------------------------------------------------
# Discriminated union for deserialization
# ---------------------------------------------------------------------------

AnyTraceEvent = Annotated[
    PipeStartEvent
    | PipeEndSuccessEvent
    | PipeEndErrorEvent
    | PipeEndSkippedEvent
    | EdgeEvent
    | ControllerOutputEvent
    | BatchItemEvent
    | BatchAggregateEvent
    | ParallelCombineEvent
    | ExecutionDataEvent
    | UsageReportEvent,
    Field(discriminator="event_kind"),
]
