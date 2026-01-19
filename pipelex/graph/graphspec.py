"""GraphSpec Pydantic v2 models for representing pipeline execution graphs.

This module defines the canonical, versioned data model for Pipelex run graphs.
GraphSpec is renderer-agnostic and designed for JSON serialization.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import Self, StrEnum

# Redaction limits
MAX_PREVIEW_LENGTH = 200
MAX_STACK_LENGTH = 2000


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


def _truncate_string(value: str | None, max_length: int) -> str | None:
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
        return _truncate_string(value, MAX_PREVIEW_LENGTH)


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
        return _truncate_string(value, MAX_STACK_LENGTH)


class NodeSpec(BaseModel):
    """Specification for a node in the execution graph.

    Each node represents a pipe invocation during execution.
    """

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    node_id: str = Field(validation_alias="id", serialization_alias="id")
    kind: NodeKind
    pipe_code: str | None = None
    pipe_type: str | None = None
    status: NodeStatus
    timing: TimingSpec | None = None
    node_io: NodeIOSpec = Field(
        default_factory=NodeIOSpec,
        validation_alias="io",
        serialization_alias="io",
    )
    error: ErrorSpec | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


class EdgeSpec(BaseModel):
    """Specification for an edge in the execution graph."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    edge_id: str = Field(validation_alias="id", serialization_alias="id")
    source: str
    target: str
    kind: EdgeKind
    label: str | None = None
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
    meta: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(serialize_as_any=True, by_alias=True, indent=2)
