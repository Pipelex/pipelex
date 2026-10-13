"""TraceContext model for passing per-execution trace state through JobMetadata.

This is the serializable context that flows through pipe execution, similar to
OtelContext for OpenTelemetry tracing. It is the shared transport for two event
streams that ride on one substrate — the per-execution node tree:

- **graph** (node/edge events) → assembled into a ``GraphSpec`` for visualization;
- **usage** (cost events) → attributed to a node via ``parent_node_id`` and rendered
  into a cost report.

Both streams hang off the same node tree, so the node-minting machinery
(``make_node_id`` / ``copy_for_child`` / ``node_sequence``) is shared, not graph-only.
The node tree is always built when either stream is on — including costs-only
(``--no-graph --costs``) mode, where usage still needs ``parent_node_id`` to attribute to.

Beside the run-scoped node ids, the context carries what names an invocation in every view of a
run (``pipelex.system.invocation_path``): the path of the invocation its pipes run under, the
segment a controller gives the next pipe it runs, and the chain of execution attempts the events
written under it belong to (``pipelex.system.execution_chain``).
"""

from pydantic import BaseModel, ConfigDict, Field

from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.exceptions import InvocationPathError
from pipelex.system.execution_chain import ExecutionAttempt, make_direct_chain
from pipelex.system.invocation_path import child_path
from pipelex.system.pipe_run_mode import PipeRunMode


class TraceContext(BaseModel):
    """Serializable per-execution trace context passed through JobMetadata.

    Tracks parent-child relationships as pipes execute, building the node tree that
    both the graph stream (edges) and the usage stream (cost attribution) read from.
    Designed to be serializable for distributed environments where contextvars don't work.

    Attributes:
        graph_id: Unique identifier for this execution trace (typically pipeline_run_id).
        parent_node_id: The node ID of the parent pipe (None for root). The shared anchor —
            read by the graph stream (edges) and the usage stream (cost attribution).
        node_sequence: Monotonic counter for generating unique node IDs within this trace.
        data_inclusion: Configuration controlling which data formats to capture in IOSpec fields.
        emit_graph_events: Whether graph (node/edge) trace events should be emitted for this run
            (driven by ``is_generate_graph``). The in-memory tracer always accumulates; this only
            gates event emission onto the shared event-log transport.
        emit_usage_events: Whether usage (cost) trace events should be emitted for this run
            (driven by ``is_generate_usage``). Independent of ``emit_graph_events`` so cost reporting
            survives ``--no-graph``.
        describe_pipe_io: Whether the run builds the three I/O artifacts that describe its graphspec's
            data (driven by ``graphs_inclusion.graphspec_json``). Off for a run that writes no
            graphspec, and for validate's own graph dry run, which already built them for its report.
        run_mode: Whether the run is live or a dry run. Every trace event the run emits states it, the
            usage events an activity emits included, which have this context and nothing else of the run.
            Required, with no default: a context built without it would stamp a dry run's events as live.
        parent_path: The invocation path of the pipe whose children run under this context, None above the
            run's entry pipe. It is absolute from the entry pipe, whichever execution reads it: a batch item's
            own execution receives its item's path as the prefix of every path it stamps.
        child_segment: The segment, under ``parent_path``, that a controller gives the next pipe it runs. Set
            on the copy of the context the controller hands that pipe, and never carried further down.
        chain: The execution attempts the events written under this context belong to, from the run's own
            execution down to the one writing them: its lineage followed by its own ``{execution, attempt}``.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    graph_id: str = Field(description="Unique identifier for this execution trace (typically the pipeline run id)")
    tracer_key: str | None = Field(default=None, description="Lookup key in GraphTracerManager. Defaults to graph_id when None.")
    parent_node_id: str | None = Field(default=None, description="Node ID of the parent pipe, None for root")
    node_sequence: int = Field(default=0, description="Monotonic counter for generating node IDs")
    data_inclusion: DataInclusionConfig = Field(description="Controls which data formats to capture")
    emit_graph_events: bool = Field(default=True, description="Whether to emit graph (node/edge) trace events")
    emit_usage_events: bool = Field(default=True, description="Whether to emit usage (cost) trace events")
    describe_pipe_io: bool = Field(default=True, description="Whether to build the I/O artifacts describing the graphspec's data")
    run_mode: PipeRunMode = Field(strict=False, description="Whether the run is live or a dry run, stated by whoever opens the trace")
    parent_path: str | None = Field(default=None, description="Invocation path of the pipe whose children run under this context")
    child_segment: str | None = Field(default=None, description="Segment a controller gives the next pipe it runs, under parent_path")
    chain: list[ExecutionAttempt] = Field(
        default_factory=make_direct_chain,
        min_length=1,
        description="The execution attempts this context's events belong to, ending with the one writing them",
    )

    @property
    def lookup_key(self) -> str:
        """Key for looking up the tracer in GraphTracerManager."""
        return self.tracer_key or self.graph_id

    @property
    def own_attempt(self) -> ExecutionAttempt:
        """The attempt of the execution that writes the events under this context."""
        return self.chain[-1]

    @property
    def lineage(self) -> list[ExecutionAttempt]:
        """The attempts the writing execution was dispatched under, empty for the run's own execution."""
        return self.chain[:-1]

    def with_child_segment(self, *, segment: str) -> "TraceContext":
        """A copy of this context naming the place, under its parent path, of the next pipe a controller runs."""
        return self.model_copy(update={"child_segment": segment})

    def invocation_path(self, *, pipe_ref: str) -> str:
        """The path of the invocation of a pipe started under this context.

        The run's entry pipe, started above any parent path, is named by its `pipe_ref`. Any other pipe is named by
        the parent path followed by the segment its controller gave it.

        Args:
            pipe_ref: The `domain.code` reference of the pipe started, which names the run's entry pipe.

        Raises:
            InvocationPathError: A pipe started under a parent path without a segment, or with a segment and no
                parent path to put it under.
        """
        if self.parent_path is None:
            if self.child_segment is not None:
                msg = f"The pipe '{pipe_ref}' was given the segment '{self.child_segment}' with no parent invocation to place it under."
                raise InvocationPathError(msg)
            return pipe_ref
        if self.child_segment is None:
            msg = (
                f"The pipe '{pipe_ref}' started under the invocation '{self.parent_path}' without the segment its "
                "controller gives it, so its invocation path cannot be derived."
            )
            raise InvocationPathError(msg)
        return child_path(parent_path=self.parent_path, segment=self.child_segment)

    def make_node_id(self) -> str:
        """Generate a unique node ID within this trace.

        Returns:
            A unique node ID in format "{graph_id}:node_{sequence}".
        """
        return f"{self.graph_id}:node_{self.node_sequence}"

    def copy_for_child(self, child_node_id: str, *, next_sequence: int, invocation_path: str | None) -> "TraceContext":
        """Create a child context for a nested pipe execution.

        Args:
            child_node_id: The node ID assigned to the child pipe.
            next_sequence: The next sequence number for the child context.
            invocation_path: The child pipe's invocation path, which the pipes it runs continue; None for a node that
                is no invocation, such as a binding step, under which no pipe runs.

        Returns:
            A new TraceContext with updated parent_node_id, node_sequence and parent_path, and no child segment.
        """
        return TraceContext(
            graph_id=self.graph_id,
            tracer_key=self.tracer_key,
            parent_node_id=child_node_id,
            node_sequence=next_sequence,
            data_inclusion=self.data_inclusion,
            emit_graph_events=self.emit_graph_events,
            emit_usage_events=self.emit_usage_events,
            describe_pipe_io=self.describe_pipe_io,
            run_mode=self.run_mode,
            parent_path=invocation_path,
            child_segment=None,
            chain=list(self.chain),
        )
