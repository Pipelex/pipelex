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
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    graph_id: str = Field(description="Unique identifier for the execution graph")
    parent_node_id: str | None = Field(default=None, description="Node ID of the parent pipe, None for root")
    node_sequence: int = Field(default=0, description="Monotonic counter for generating node IDs")
    data_inclusion: DataInclusionConfig = Field(description="Controls which data formats to capture")

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
            parent_node_id=child_node_id,
            node_sequence=next_sequence,
            data_inclusion=self.data_inclusion,
        )
