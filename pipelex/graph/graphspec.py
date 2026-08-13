"""GraphSpec Pydantic v2 models for representing pipeline execution graphs.

This module defines the canonical, versioned data model for Pipelex run graphs.
GraphSpec is renderer-agnostic and designed for JSON serialization.
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

# Redaction limits
MAX_PREVIEW_LENGTH = 200
MAX_STACK_LENGTH = 2000

# Format tag stored in GraphSpec.meta so external tooling (e.g. the VS Code
# graph viewer) can recognize a JSON file as a Pipelex execution graph.
GRAPHSPEC_FORMAT = "mthds"


class GraphSpecMode(StrEnum):
    """Provenance mode for a GraphSpec."""

    DRY = "dry"
    LIVE = "live"
    STATIC = "static"


def make_graphspec_meta(*, mode: GraphSpecMode, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build canonical GraphSpec metadata while preserving caller extras."""
    meta = dict(extra or {})
    meta["format"] = GRAPHSPEC_FORMAT
    meta["mode"] = mode
    return meta


class NodeKind(StrEnum):
    """Types of nodes in the execution graph."""

    PIPE_CALL = "pipe_call"
    CONTROLLER = "controller"
    OPERATOR = "operator"
    INPUT = "input"
    OUTPUT = "output"
    ARTIFACT = "artifact"
    ERROR = "error"


class NodeStatus(StrEnum):
    """Execution status of a node."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELED = "canceled"


class EdgeKind(StrEnum):
    """Types of edges in the execution graph."""

    CONTROL = "control"
    DATA = "data"
    CONTAINS = "contains"
    SELECTED_OUTCOME = "selected_outcome"
    BATCH_ITEM = "batch_item"  # list → item extraction during batch iteration
    BATCH_AGGREGATE = "batch_aggregate"  # items → output list aggregation
    PARALLEL_COMBINE = "parallel_combine"  # branch outputs → combined output in PipeParallel

    @property
    def is_data(self) -> bool:
        match self:
            case EdgeKind.DATA:
                return True
            case (
                EdgeKind.CONTROL
                | EdgeKind.CONTAINS
                | EdgeKind.SELECTED_OUTCOME
                | EdgeKind.BATCH_ITEM
                | EdgeKind.BATCH_AGGREGATE
                | EdgeKind.PARALLEL_COMBINE
            ):
                return False

    @property
    def is_contains(self) -> bool:
        match self:
            case EdgeKind.CONTAINS:
                return True
            case (
                EdgeKind.CONTROL
                | EdgeKind.DATA
                | EdgeKind.SELECTED_OUTCOME
                | EdgeKind.BATCH_ITEM
                | EdgeKind.BATCH_AGGREGATE
                | EdgeKind.PARALLEL_COMBINE
            ):
                return False

    @property
    def is_selected_outcome(self) -> bool:
        match self:
            case EdgeKind.SELECTED_OUTCOME:
                return True
            case EdgeKind.CONTROL | EdgeKind.DATA | EdgeKind.CONTAINS | EdgeKind.BATCH_ITEM | EdgeKind.BATCH_AGGREGATE | EdgeKind.PARALLEL_COMBINE:
                return False

    @property
    def is_batch_item(self) -> bool:
        match self:
            case EdgeKind.BATCH_ITEM:
                return True
            case (
                EdgeKind.CONTROL
                | EdgeKind.DATA
                | EdgeKind.CONTAINS
                | EdgeKind.SELECTED_OUTCOME
                | EdgeKind.BATCH_AGGREGATE
                | EdgeKind.PARALLEL_COMBINE
            ):
                return False

    @property
    def is_batch_aggregate(self) -> bool:
        match self:
            case EdgeKind.BATCH_AGGREGATE:
                return True
            case EdgeKind.CONTROL | EdgeKind.DATA | EdgeKind.CONTAINS | EdgeKind.SELECTED_OUTCOME | EdgeKind.BATCH_ITEM | EdgeKind.PARALLEL_COMBINE:
                return False

    @property
    def is_parallel_combine(self) -> bool:
        match self:
            case EdgeKind.PARALLEL_COMBINE:
                return True
            case EdgeKind.CONTROL | EdgeKind.DATA | EdgeKind.CONTAINS | EdgeKind.SELECTED_OUTCOME | EdgeKind.BATCH_ITEM | EdgeKind.BATCH_AGGREGATE:
                return False


def _truncate_string(value: str | None, *, max_length: int) -> str | None:
    """Truncate a string to max_length with ellipsis if needed."""
    if value is None:
        return None
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


class PipelineRef(BaseModel):
    """Reference to the pipeline that was executed."""

    model_config = ConfigDict(extra="forbid", strict=True)

    domain: str | None = None
    main_pipe: str | None = None
    entrypoint: str | None = None


class TimingSpec(BaseModel):
    """Timing information for a node execution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    started_at: datetime = Field(strict=False)
    ended_at: datetime = Field(strict=False)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration(self) -> float:
        """Duration in seconds, included in JSON serialization."""
        return (self.ended_at - self.started_at).total_seconds()

    # filter out the duration field (computed, not stored)
    @model_validator(mode="before")
    @classmethod
    def validate_duration(cls, data: dict[str, Any] | Self) -> dict[str, Any] | Self:
        """Filter out the duration field from dict input without mutating the original."""
        if isinstance(data, dict) and "duration" in data:
            return {key: value for key, value in data.items() if key != "duration"}
        return data


class IOSpec(BaseModel):
    """Specification for an input or output variable.

    Previews are automatically truncated to MAX_PREVIEW_LENGTH to prevent
    accidental storage of large payloads or sensitive data.

    The optional `data` field can hold the full serialized content when
    full data capture is enabled (via --graph-full-data CLI option).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    concept: str | None = None
    content_type: str | None = None
    preview: str | None = None
    size: int | None = None
    digest: str | None = None
    data: str | dict[str, Any] | list[str] | list[dict[str, Any]] | None = None
    data_text: str | None = None
    data_html: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("preview", mode="after")
    @classmethod
    def truncate_preview(cls, value: str | None) -> str | None:
        """Truncate preview to MAX_PREVIEW_LENGTH."""
        return _truncate_string(value, max_length=MAX_PREVIEW_LENGTH)


def output_digest_is_optional(*, output_specs: Sequence[IOSpec], digest: str) -> bool:
    """Whether a producer registered ``digest`` as a declared-optional (`?`) output.

    The optional marker rides the output IOSpec's ``extra`` dict (set at the pipe-run
    epilogue from the pipe's declared output presence). One helper for both graph builders
    (in-process GraphTracer and the event-replay assembler) so the optional-edge computation
    cannot drift between them.
    """
    for output_spec in output_specs:
        if output_spec.digest == digest:
            return bool(output_spec.extra.get("optional"))
    return False


class NodeIOSpec(BaseModel):
    """Input/output specification for a node."""

    model_config = ConfigDict(extra="forbid", strict=True)

    inputs: list[IOSpec] = Field(default_factory=empty_list_factory_of(IOSpec))
    outputs: list[IOSpec] = Field(default_factory=empty_list_factory_of(IOSpec))


class ErrorSpec(BaseModel):
    """Error information for failed nodes.

    Stack traces are automatically truncated to MAX_STACK_LENGTH.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    error_type: str
    message: str
    stack: str | None = None

    @field_validator("stack", mode="after")
    @classmethod
    def truncate_stack(cls, value: str | None) -> str | None:
        """Truncate stack trace to MAX_STACK_LENGTH."""
        return _truncate_string(value, max_length=MAX_STACK_LENGTH)


class ModelUsageSpec(BaseModel):
    """What one inference model actually did for a node.

    This is the only place the graph records the model that **ran**. Everything else
    in a GraphSpec that names a model records what was *asked for*:
    ``execution_data.resolved_model`` holds the handle the pipe resolved to — which may
    still be an alias (``@default-premium``) — and the pipe blueprint holds the authored
    choice (``$writing-factual``). Those are three rungs of one ladder, and only this
    rung is the outcome: it survives alias resolution, deck defaults, and any fallback
    or retry that landed somewhere other than what was requested.

    A node genuinely uses more than one model in ordinary cases — a ``PipeLLM``'s text
    pass and its object-structuring pass resolve separately — so a node's models are a
    LIST. Collapsing them to "the model" would be wrong in exactly the way a single
    ``cost`` for mixed rated/unrated calls is wrong.

    ``cost`` follows ``NodeUsageSpec`` invariant 2: ``None`` iff no call to this model
    carried a rate table.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    inference_model_name: str
    inference_model_id: str
    # Kind of inference: "llm", "img_gen", "extract", "search". The discriminator a
    # consumer needs before displaying token counts: extract/search/img_gen are billed
    # PER REQUEST, and that price is encoded by putting 1_000_000 in each token
    # category (rates are per-million), so their "tokens" are a scaled request counter.
    model_type: str
    inference_calls: int = 0
    rated_inference_calls: int = 0
    cost: float | None = None


class NodeUsageSpec(BaseModel):
    """Inference usage attributed to one graph node.

    Field names mirror the already-shipped client-facing ``TokensUsageRecord``
    (``reporting/usage_records.py``) so the graph does not introduce a fifth vocabulary
    for numbers this codebase already names four ways (``TokenCategory``,
    ``LLMTokenCostReportField``, ``GenAISpanAttr``, ``PostHogAttr``).

    INVARIANTS — the UI and every other consumer branch on these, not on guesses about
    why a number is missing:

      1. ``NodeSpec.usage is None`` <=> no usage was reported anywhere in the run —
         either usage collection was off, or the run made zero inference calls. As soon
         as ONE usage event was seen, EVERY node carries a spec, zeroed where nothing
         ran. A controller, a lifted pipe, and a PipeFunc all get ``inference_calls=0``,
         never ``usage=None``. So the field is all-or-nothing across a graph: it never
         distinguishes "this node was not measured" from "that node was".

      2. ``cost is None`` <=> ``rated_inference_calls == 0``. Nothing else. "Made no
         call" and "made only unrated calls" both land here and are told apart by
         ``inference_calls``.

      3. ``inference_calls > rated_inference_calls > 0`` => ``cost`` is a LOWER BOUND,
         not a total: some of this node's calls carried no rate table. The UI must mark
         it (a leading "≥").

      4. ``total_tokens`` is input_joined + output — the same definition as
         ``AggregatedCosts.total_nb_tokens``. It is NOT the sum of
         ``nb_tokens_by_category``: ``input_cached`` is a SUBSET of ``input``, not
         additive (see ``usage_records.py``), so summing double-counts. Never sum the
         dict; read this field.

      5. ``cost_input`` + ``cost_output`` == ``cost`` (to float precision). They are
         the same number split by direction, not extra charges, and they are None on
         exactly the same condition.

      6. ``by_model`` names the models that actually RAN, and its ``inference_calls``
         sum to this spec's own. It is a list because one node routinely uses more
         than one model (a PipeLLM's text pass and its object pass resolve
         separately). Ordered by descending calls, then by name, so a consumer can
         take the first entry as the dominant model without sorting.

    The same invariants hold for the ``subtree_*`` half, which covers this node plus
    every descendant (rolled up in the assembler, once, so no consumer re-derives it
    and disagrees).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    # This node's own inference.
    inference_calls: int = 0
    rated_inference_calls: int = 0
    nb_tokens_by_category: dict[str, int] = Field(default_factory=dict)
    total_tokens: int = 0
    cost: float | None = None
    # Components of ``cost``: input is the joined input cost (non-cached + cached).
    # Both follow invariant 2 alongside ``cost`` — None iff nothing was priced.
    cost_input: float | None = None
    cost_output: float | None = None
    by_model: list[ModelUsageSpec] = Field(default_factory=empty_list_factory_of(ModelUsageSpec))

    # This node plus every descendant.
    subtree_inference_calls: int = 0
    subtree_rated_inference_calls: int = 0
    subtree_nb_tokens_by_category: dict[str, int] = Field(default_factory=dict)
    subtree_total_tokens: int = 0
    subtree_cost: float | None = None
    subtree_cost_input: float | None = None
    subtree_cost_output: float | None = None
    subtree_by_model: list[ModelUsageSpec] = Field(default_factory=empty_list_factory_of(ModelUsageSpec))


class GraphUsageSpec(BaseModel):
    """Run-level inference usage for a whole GraphSpec.

    ``total`` covers every usage the run reported, attributed or not — it is the graph's
    comparand for the cost report's own total. ``unattributed`` is the part that named no
    live node (the ``UNATTRIBUTED_NODE_ID`` fallback, or a node that never emitted a
    start event): surfaced as its own bucket rather than dropped, so the graph's total
    can never silently disagree with the cost report's.

    Both reuse ``NodeUsageSpec`` — one usage shape in the contract, not two. Neither has
    a subtree distinct from itself, so their ``subtree_*`` fields repeat their own.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    total: NodeUsageSpec
    unattributed: NodeUsageSpec


class NodeSpec(BaseModel):
    """Specification for a node in the execution graph.

    Each node represents a pipe invocation during execution.
    """

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    node_id: str = Field(validation_alias="id", serialization_alias="id")
    kind: NodeKind = Field(strict=False)
    pipe_code: str | None = None
    pipe_type: str | None = None
    description: str | None = None
    domain_code: str | None = None
    status: NodeStatus = Field(strict=False)
    # Why a `skipped` node was lifted (names the absent input); None for every other status.
    skip_reason: str | None = None
    timing: TimingSpec | None = None
    node_io: NodeIOSpec = Field(
        default_factory=NodeIOSpec,
        validation_alias="io",
        serialization_alias="io",
    )
    error: ErrorSpec | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    # Inference usage attributed to this node; None under NodeUsageSpec invariant 1.
    usage: NodeUsageSpec | None = None
    execution_data: dict[str, Any] = Field(default_factory=dict)


class EdgeSpec(BaseModel):
    """Specification for an edge in the execution graph."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    edge_id: str = Field(validation_alias="id", serialization_alias="id")
    source: str
    target: str
    kind: EdgeKind = Field(strict=False)
    # A data edge fed by a declared-optional (`?`) output: the value may be absent in other runs.
    optional: bool = False
    label: str | None = None
    # For batch edges, specify the stuff digests for renderers to connect stuff nodes directly
    source_stuff_digest: str | None = None
    target_stuff_digest: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphSpec(BaseModel):
    """The canonical specification for a pipeline execution graph.

    This is the top-level model representing a complete run graph.
    It is versioned and designed for JSON serialization.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    graph_id: str
    created_at: datetime
    pipeline_ref: PipelineRef = Field(default_factory=PipelineRef)
    nodes: list[NodeSpec] = Field(default_factory=empty_list_factory_of(NodeSpec))
    edges: list[EdgeSpec] = Field(default_factory=empty_list_factory_of(EdgeSpec))
    # Run-level usage rollup; None under NodeUsageSpec invariant 1, alongside every node's.
    usage: GraphUsageSpec | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    pipe_registry: dict[str, dict[str, Any]] = Field(default_factory=dict)
    concept_registry: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensure_meta_contract(self) -> Self:
        existing_format = self.meta.get("format")
        if existing_format is None:
            self.meta["format"] = GRAPHSPEC_FORMAT
        elif existing_format != GRAPHSPEC_FORMAT:
            msg = f"GraphSpec.meta['format'] must be '{GRAPHSPEC_FORMAT}', got '{existing_format}'"
            raise ValueError(msg)
        if "mode" in self.meta:
            existing_mode = self.meta["mode"]
            try:
                self.meta["mode"] = GraphSpecMode(existing_mode)
            except ValueError as exc:
                allowed_modes = ", ".join(mode for mode in GraphSpecMode)
                msg = f"GraphSpec.meta['mode'] must be one of: {allowed_modes}; got '{existing_mode}'"
                raise ValueError(msg) from exc
        return self

    def to_json(self) -> str:
        return self.model_dump_json(serialize_as_any=True, by_alias=True, indent=2)
