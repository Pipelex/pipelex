"""Trace event models for distributed pipeline tracing.

Defines serializable event types that capture the same information as
GraphTracer's in-memory accumulation, but as immutable records suitable
for NDJSON file storage and cross-worker graph assembly.
"""

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from functools import cached_property
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from typing_extensions import override

from pipelex.errors.problem import PipelexProblem
from pipelex.graph.condition_output_merge import ConditionOutputMerge
from pipelex.graph.graphspec import EdgeKind, IOSpec, NodeKind, cap_error_stack
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.system.execution_chain import ExecutionAttempt, execution_chain_key
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


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
    CONDITION_OUTPUT_MERGE = "condition_output_merge"
    BATCH_FANNED_OUT = "batch_fanned_out"
    CONDITION_RESOLVED = "condition_resolved"
    EXECUTION_DATA = "execution_data"
    USAGE_REPORT = "usage_report"


class TraceEvent(BaseModel):
    """Base model for all trace events.

    The fields of the hosted progress contract (`conformance/specs/pipelex-platform-api.md`, "How the runtime
    carries them") are read off these: `execution` is `workflow_id`, `attempt` and `lineage` are their own, `at` is
    `timestamp` and `sequence` is `sequence`.

    Shared fields:
    - pipeline_run_id: identifies the pipeline execution
    - workflow_id: the id of the workflow whose code emitted the event, the same in each of its attempts, or
        "direct" in the runtime's direct mode. It names the event's execution.
    - attempt: the attempt of that workflow which emitted the event, counting from 1; 1 in direct mode.
    - lineage: the attempts that workflow was dispatched under, from the run's own workflow down to the one that
        dispatched it; empty for the run's own workflow. An event's chain is its lineage followed by its own
        `{execution, attempt}`, and a higher attempt of an execution supersedes the earlier one and everything it
        dispatched (`pipelex.system.execution_chain`).
    - path: the invocation path of the pipe run the event is about (`pipelex.system.invocation_path`): the batch's for
        a fan-out, the condition's for a resolution, the target's for an edge, the pipe whose work an inference
        served for a usage report. None for an event about no invocation, such as a binding step's.
    - writer_id: identifies the emitting event-log instance, so two writers
        sharing the same (pipeline_run_id, workflow_id) partition can emit
        independent sequence streams without colliding. Defaults to "primary",
        which preserves the legacy single-writer NDJSON file naming; non-default values
        come from the per-process activity event log used by separate-process workers.
        It names no execution: one writer may carry the events of several at once.
    - event_kind: discriminator for the event subclass (defined on each subclass as Literal)
    - mode: whether the run that emitted the event is live or a dry run. Every event of one run
        carries the same mode, so a reader tells dry events from live ones by this field alone.
    - timestamp: UTC, when the event happened: a start's start, an end's end, a decision's moment. It is recorded
        once, so every write of one event carries the same value; ordering and deduplication never read it.
    - sequence: per-writer monotonic counter, for ordering and deduplication

    A store keeps apart every two events whose chain, writer or sequence differ (`store_key`): keyed on the workflow,
    the writer and the sequence alone, a workflow's new attempt would overwrite the events of its earlier one.

    An event is frozen, since it records what happened: its chain, its chain key and its store key are computed from its
    fields once, the first time they are read, and kept, as every read and every assembly of a run reads them for each
    of its events.
    """

    model_config = ConfigDict(frozen=True)

    pipeline_run_id: str
    workflow_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    lineage: list[ExecutionAttempt]
    path: str | None
    writer_id: str = "primary"
    mode: PipeRunMode
    timestamp: datetime
    sequence: int

    @cached_property
    def chain(self) -> list[ExecutionAttempt]:
        """The attempts from the run's own workflow down to the one that emitted this event."""
        return [*self.lineage, ExecutionAttempt(execution=self.workflow_id, attempt=self.attempt)]

    @cached_property
    def chain_key(self) -> str:
        """One string naming this event's chain, distinct for every two chains that differ."""
        return execution_chain_key(chain=self.chain)

    @cached_property
    def store_key(self) -> tuple[str, str, str, int]:
        """What tells this event apart from every other event of its run in a store: its chain, its writer, its kind
        and its sequence. Two writes with the same key are one event, written again by a replay.
        """
        return (self.chain_key, self.writer_id, type(self).__name__, self.sequence)

    @override
    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A copy of this event, which computes its keys again: an update can change the fields they are read from."""
        copied = super().model_copy(update=update, deep=deep)
        for cached_name in _CACHED_EVENT_KEYS:
            vars(copied).pop(cached_name, None)
        return copied


# The names under which a trace event keeps the keys it computed from its fields.
_CACHED_EVENT_KEYS: tuple[str, ...] = ("chain", "chain_key", "store_key")


# ---------------------------------------------------------------------------
# Event subclasses
# ---------------------------------------------------------------------------


class PipeStartEvent(TraceEvent):
    """Emitted when a pipe begins execution, before it runs anything."""

    event_kind: Literal[TraceEventKind.PIPE_START] = TraceEventKind.PIPE_START
    node_id: str
    parent_node_id: str | None = None
    pipe_code: str
    pipe_ref: str | None
    """The `domain.code` reference of the pipe; None on a binding step's node, which runs no pipe."""
    pipe_type: str
    node_kind: NodeKind
    description: str | None = None
    domain_code: str | None = None
    input_specs: list[IOSpec] = Field(default_factory=empty_list_factory_of(IOSpec))
    pipe_data: dict[str, Any] = Field(default_factory=dict)
    concept_data: list[dict[str, Any]] = Field(default_factory=empty_list_factory_of(dict))
    step_count: int | None = None
    """On a PipeSequence, the number of steps its author wrote. The binding a sequence writes for a dotted
    `batch_over` is no step of the author's and is not counted. None on every other pipe."""
    branch_count: int | None = None
    """On a PipeParallel, the number of its branches. None on every other pipe."""


class PipeEndSuccessEvent(TraceEvent):
    """Emitted when a pipe completes successfully."""

    event_kind: Literal[TraceEventKind.PIPE_END_SUCCESS] = TraceEventKind.PIPE_END_SUCCESS
    node_id: str
    pipe_code: str
    pipe_ref: str | None
    pipe_type: str
    ended_at: datetime
    output_spec: IOSpec | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    output_concept_data: dict[str, Any] = Field(default_factory=dict)


class PipeEndErrorEvent(TraceEvent):
    """Emitted when a pipe fails.

    Its `error` is the problem that ended the pipe, in the caller's view, located at the pipe; `error_stack` is the
    stack trace of the error, when the graph's data inclusion asks for it, capped as the graph's node caps it, since
    the event reaches every trace subscriber before any node is built from it.
    """

    event_kind: Literal[TraceEventKind.PIPE_END_ERROR] = TraceEventKind.PIPE_END_ERROR
    node_id: str
    pipe_code: str
    pipe_ref: str | None
    pipe_type: str
    ended_at: datetime
    error: PipelexProblem
    error_stack: str | None = None

    @field_validator("error_stack", mode="after")
    @classmethod
    def cap_stack(cls, value: str | None) -> str | None:
        return cap_error_stack(stack=value)


class PipeEndSkippedEvent(TraceEvent):
    """Emitted when a pipe is lifted (skipped) because a plain input resolved absent (D3).

    A skip is a successful outcome — the run continues and the pipe's output is a recorded
    absence — but it gets its own node state so graph consumers can render it distinctly.
    """

    event_kind: Literal[TraceEventKind.PIPE_END_SKIPPED] = TraceEventKind.PIPE_END_SKIPPED
    node_id: str
    pipe_code: str
    pipe_ref: str | None
    pipe_type: str
    ended_at: datetime
    skip_reason: str
    output_spec: IOSpec | None = None
    """A lifted pipe with a PLURAL output still writes a real empty-list Stuff (D4) — its spec
    rides the skip event so the digest registers in the producer map and downstream DATA edges
    resolve. None for a singular output (a recorded absence has no payload)."""
    output_concept_data: dict[str, Any] = Field(default_factory=dict)


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


class ConditionOutputMergeEvent(TraceEvent):
    """Emitted when a dry-run condition merges its outcomes' outputs onto its own output digest.

    Applied by the assembler once the graph is built, through the same rewrite as GraphTracer's.
    """

    event_kind: Literal[TraceEventKind.CONDITION_OUTPUT_MERGE] = TraceEventKind.CONDITION_OUTPUT_MERGE
    merge: ConditionOutputMerge


class BatchFannedOutEvent(TraceEvent):
    """Emitted when a PipeBatch knows how many items it runs, before it starts any of them.

    A live reader learns the batch's width the moment it is fixed, so it never has to guess it from the
    items that have started.
    """

    event_kind: Literal[TraceEventKind.BATCH_FANNED_OUT] = TraceEventKind.BATCH_FANNED_OUT
    node_id: str
    """The PipeBatch's own node."""
    item_count: int = Field(ge=0)
    branch_pipe_code: str
    """The bare code of the pipe each item runs."""
    branch_pipe_ref: str
    """The `domain.code` reference of the pipe each item runs."""
    branch_pipe_type: str
    """The type of the pipe each item runs, such as `PipeSequence` or `PipeLLM`."""


class ConditionResolvedEvent(TraceEvent):
    """Emitted when a live PipeCondition has chosen its outcome, before the chosen pipe starts.

    A dry run emits none, since its condition runs the pipe of every outcome.
    """

    event_kind: Literal[TraceEventKind.CONDITION_RESOLVED] = TraceEventKind.CONDITION_RESOLVED
    node_id: str
    """The PipeCondition's own node."""
    rendered_value: str
    """The value the condition's expression rendered. It may quote text of the method, or of a library the method
    depends on, so it is kept for whoever reads the trace and never reaches a problem's parameters."""
    selected_outcome: str | None
    """The key of the outcome map the rendered value matched, or None when it matched none and the condition took its
    default outcome: `"default"` can itself be a key of an outcome map, so it cannot stand for the default."""


class ExecutionDataEvent(TraceEvent):
    """Emitted when a pipe registers execution metadata (rendered prompts, resolved models, etc.)."""

    event_kind: Literal[TraceEventKind.EXECUTION_DATA] = TraceEventKind.EXECUTION_DATA
    node_id: str
    execution_data: dict[str, Any] = Field(default_factory=dict)


# node_id stamped on a UsageReportEvent emitted outside any pipe context (no
# parent_node_id on the trace context). The assembler routes it to
# GraphUsageSpec.unattributed rather than dropping it.
UNATTRIBUTED_NODE_ID = "unknown"


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
    | ConditionOutputMergeEvent
    | BatchFannedOutEvent
    | ConditionResolvedEvent
    | ExecutionDataEvent
    | UsageReportEvent,
    Field(discriminator="event_kind"),
]


def json_invalid_message(*, validation_error: ValidationError) -> str | None:
    """The parse error of a stored trace event that is not JSON at all, or `None` when it parsed and was refused.

    `validate_json` reports unparseable input as a `json_invalid` entry rather than raising `JSONDecodeError`, so
    the two cases are told apart by the entry's type. The entry's message says where the parse stopped and quotes
    nothing, while the exception's own text quotes the stored record whole, traced values included: a reader that
    logs why it skipped a record logs this message, never the exception's text.
    """
    for error in validation_error.errors():
        if error["type"] == "json_invalid":
            return error["msg"]
    return None
