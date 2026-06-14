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
"""

from pydantic import BaseModel, ConfigDict, Field

from pipelex.graph.graph_config import DataInclusionConfig


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
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    graph_id: str = Field(description="Unique identifier for this execution trace (typically the pipeline run id)")
    tracer_key: str | None = Field(default=None, description="Lookup key in GraphTracerManager. Defaults to graph_id when None.")
    parent_node_id: str | None = Field(default=None, description="Node ID of the parent pipe, None for root")
    node_sequence: int = Field(default=0, description="Monotonic counter for generating node IDs")
    data_inclusion: DataInclusionConfig = Field(description="Controls which data formats to capture")
    emit_graph_events: bool = Field(default=True, description="Whether to emit graph (node/edge) trace events")
    emit_usage_events: bool = Field(default=True, description="Whether to emit usage (cost) trace events")

    @property
    def lookup_key(self) -> str:
        """Key for looking up the tracer in GraphTracerManager."""
        return self.tracer_key or self.graph_id

    def make_node_id(self) -> str:
        """Generate a unique node ID within this trace.

        Returns:
            A unique node ID in format "{graph_id}:node_{sequence}".
        """
        return f"{self.graph_id}:node_{self.node_sequence}"

    def copy_for_child(self, child_node_id: str, *, next_sequence: int) -> "TraceContext":
        """Create a child context for a nested pipe execution.

        Args:
            child_node_id: The node ID assigned to the child pipe.
            next_sequence: The next sequence number for the child context.

        Returns:
            A new TraceContext with updated parent_node_id and node_sequence.
        """
        return TraceContext(
            graph_id=self.graph_id,
            tracer_key=self.tracer_key,
            parent_node_id=child_node_id,
            node_sequence=next_sequence,
            data_inclusion=self.data_inclusion,
            emit_graph_events=self.emit_graph_events,
            emit_usage_events=self.emit_usage_events,
        )
