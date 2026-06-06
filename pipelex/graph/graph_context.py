"""GraphContext model for passing graph tracing state through JobMetadata.

This is the serializable context that flows through pipe execution,
similar to OtelContext for OpenTelemetry tracing.
"""

from pydantic import BaseModel, ConfigDict, Field

from pipelex.graph.graph_config import DataInclusionConfig


class GraphContext(BaseModel):
    """Serializable context for graph tracing passed through JobMetadata.

    This context enables building a GraphSpec by tracking parent-child
    relationships as pipes execute. It's designed to be serializable
    for distributed environments where contextvars don't work.

    Attributes:
        graph_id: Unique identifier for this execution graph (typically pipeline_run_id).
        parent_node_id: The node ID of the parent pipe (None for root).
        node_sequence: Monotonic counter for generating unique node IDs within this graph.
        data_inclusion: Configuration controlling which data formats to capture in IOSpec fields.
        emit_graph_events: Whether graph (node/edge) trace events should be emitted for this run
            (driven by ``is_generate_graph``). The in-memory tracer always accumulates; this only
            gates event emission onto the shared event-log transport.
        emit_usage_events: Whether usage (cost) trace events should be emitted for this run
            (driven by ``is_generate_costs``). Independent of ``emit_graph_events`` so cost reporting
            survives ``--no-graph``.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    graph_id: str = Field(description="Unique identifier for the execution graph")
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
        """Generate a unique node ID within this graph.

        Returns:
            A unique node ID in format "{graph_id}:node_{sequence}".
        """
        return f"{self.graph_id}:node_{self.node_sequence}"

    def copy_for_child(self, child_node_id: str, next_sequence: int) -> "GraphContext":
        """Create a child context for a nested pipe execution.

        Args:
            child_node_id: The node ID assigned to the child pipe.
            next_sequence: The next sequence number for the child context.

        Returns:
            A new GraphContext with updated parent_node_id and node_sequence.
        """
        return GraphContext(
            graph_id=self.graph_id,
            tracer_key=self.tracer_key,
            parent_node_id=child_node_id,
            node_sequence=next_sequence,
            data_inclusion=self.data_inclusion,
            emit_graph_events=self.emit_graph_events,
            emit_usage_events=self.emit_usage_events,
        )
