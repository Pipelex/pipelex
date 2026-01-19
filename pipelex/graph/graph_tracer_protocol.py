from datetime import datetime
from typing import Protocol

from typing_extensions import override

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graphspec import EdgeKind, GraphSpec, IOSpec, NodeKind


class GraphTracerProtocol(Protocol):
    """Protocol for building GraphSpec during pipe execution.

    Similar to PipelineTrackerProtocol but focused on execution tracing
    rather than data flow tracking.
    """

    def setup(
        self,
        graph_id: str,
        data_inclusion: DataInclusionConfig,
        pipeline_ref_domain: str | None = None,
        pipeline_ref_main_pipe: str | None = None,
    ) -> GraphContext:
        """Initialize tracing for a new pipeline run.

        Args:
            graph_id: Unique identifier for this execution graph.
            data_inclusion: Configuration controlling which data formats to capture in IOSpec fields.
            pipeline_ref_domain: Optional domain name for the pipeline.
            pipeline_ref_main_pipe: Optional main pipe name.

        Returns:
            Initial GraphContext to pass through JobMetadata.
        """
        ...

    def teardown(self) -> GraphSpec | None:
        """Finalize tracing and return the built GraphSpec.

        Returns:
            The completed GraphSpec, or None if tracing was disabled.
        """
        ...

    def on_pipe_start(
        self,
        graph_context: GraphContext,
        pipe_code: str,
        pipe_type: str,
        node_kind: NodeKind,
        started_at: datetime,
        input_specs: list[IOSpec] | None = None,
    ) -> tuple[str, GraphContext]:
        """Record the start of a pipe execution.

        Args:
            graph_context: Current graph context from JobMetadata.
            pipe_code: The pipe code being executed.
            pipe_type: The pipe type (e.g., "PipeLLM", "PipeSequence").
            node_kind: The kind of node (controller, operator, etc.).
            started_at: When the pipe started executing.
            input_specs: Optional list of IOSpec describing the inputs consumed.

        Returns:
            Tuple of (node_id for this pipe, updated GraphContext for children).
        """
        ...

    def on_pipe_end_success(
        self,
        node_id: str,
        ended_at: datetime,
        output_preview: str | None = None,
        metrics: dict[str, float] | None = None,
        output_spec: IOSpec | None = None,
    ) -> None:
        """Record successful completion of a pipe execution.

        Args:
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe finished executing.
            output_preview: Optional truncated preview of the output.
            metrics: Optional metrics (e.g., token counts).
            output_spec: Optional IOSpec describing the output produced.
        """
        ...

    def on_pipe_end_error(
        self,
        node_id: str,
        ended_at: datetime,
        error_type: str,
        error_message: str,
        error_stack: str | None = None,
    ) -> None:
        """Record failed completion of a pipe execution.

        Args:
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe failed.
            error_type: The exception type name.
            error_message: The error message.
            error_stack: Optional stack trace.
        """
        ...

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
    ) -> None:
        """Add an edge between two nodes.

        Args:
            source_node_id: The source node ID.
            target_node_id: The target node ID.
            edge_kind: The type of edge.
            label: Optional label for the edge.
        """
        ...


class GraphTracerNoOp(GraphTracerProtocol):
    """No-operation implementation of GraphTracerProtocol.

    Use this when graph tracing is disabled.
    """

    @override
    def setup(
        self,
        graph_id: str,
        data_inclusion: DataInclusionConfig,
        pipeline_ref_domain: str | None = None,
        pipeline_ref_main_pipe: str | None = None,
    ) -> GraphContext:
        return GraphContext(
            graph_id=graph_id,
            data_inclusion=data_inclusion,
        )

    @override
    def teardown(self) -> None:
        return None

    @override
    def on_pipe_start(
        self,
        graph_context: GraphContext,
        pipe_code: str,
        pipe_type: str,
        node_kind: NodeKind,
        started_at: datetime,
        input_specs: list[IOSpec] | None = None,
    ) -> tuple[str, GraphContext]:
        node_id = graph_context.make_node_id()
        child_context = graph_context.copy_for_child(node_id, graph_context.node_sequence + 1)
        return node_id, child_context

    @override
    def on_pipe_end_success(
        self,
        node_id: str,
        ended_at: datetime,
        output_preview: str | None = None,
        metrics: dict[str, float] | None = None,
        output_spec: IOSpec | None = None,
    ) -> None:
        pass

    @override
    def on_pipe_end_error(
        self,
        node_id: str,
        ended_at: datetime,
        error_type: str,
        error_message: str,
        error_stack: str | None = None,
    ) -> None:
        pass

    @override
    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
    ) -> None:
        pass
