"""Graph tracer manager with singleton pattern for access from PipeAbstract without hub imports."""

from datetime import datetime

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graph_tracer_protocol import GraphTracerProtocol
from pipelex.graph.graphspec import EdgeKind, GraphSpec, IOSpec, NodeKind
from pipelex.system.registries.singleton import ABCSingletonMeta, MetaSingleton


class GraphTracerManager(metaclass=ABCSingletonMeta):
    """Singleton manager for graph tracing supporting multiple concurrent pipeline runs.

    This provides a way to access graph tracers without importing from hub,
    avoiding circular dependency issues. Each pipeline run gets its own tracer
    indexed by graph_id (pipeline_run_id).
    """

    def __init__(self) -> None:
        self._tracers: dict[str, GraphTracer] = {}

    ############################################################
    # Singleton access
    ############################################################

    @classmethod
    def clear_instance(cls) -> None:
        """Clear the singleton instance from MetaSingleton registry."""
        MetaSingleton.clear_subclass_instances(GraphTracerManager)

    @classmethod
    def get_instance(cls) -> "GraphTracerManager | None":
        """Get the singleton instance from MetaSingleton registry.

        This provides a way to access the graph tracer manager without importing from hub,
        avoiding circular dependency issues.
        """
        return MetaSingleton.get_subclass_instance(GraphTracerManager)  # type: ignore[type-abstract]

    @classmethod
    def get_or_create_instance(cls) -> "GraphTracerManager":
        """Get the singleton instance, creating it if it doesn't exist.

        Returns:
            The singleton GraphTracerManager instance.
        """
        instance = cls.get_instance()
        if instance is None:
            instance = cls()
        return instance

    @classmethod
    def get_instance_tracer(cls, graph_id: str) -> GraphTracerProtocol | None:
        """Get the graph tracer for a specific graph_id from the singleton instance.

        This provides a way to access the tracer without importing from hub,
        avoiding circular dependency issues.

        Args:
            graph_id: The graph/pipeline run identifier.

        Returns:
            The tracer for the given graph_id, or None if not found.
        """
        instance = cls.get_instance()
        if instance is None:
            return None
        return instance.get_tracer(graph_id)

    ############################################################
    # Private helpers
    ############################################################

    def _get_tracer(self, graph_id: str) -> GraphTracer | None:
        """Get the tracer for a specific graph_id.

        Args:
            graph_id: The graph/pipeline run identifier.

        Returns:
            The tracer if found, None otherwise.
        """
        return self._tracers.get(graph_id)

    ############################################################
    # Tracer lifecycle (per-run)
    ############################################################

    def open_tracer(
        self,
        graph_id: str,
        data_inclusion: DataInclusionConfig,
        pipeline_ref_domain: str | None = None,
        pipeline_ref_main_pipe: str | None = None,
    ) -> GraphContext:
        """Create and initialize a new tracer for a pipeline run.

        Args:
            graph_id: Unique identifier for this pipeline run.
            data_inclusion: Configuration controlling which data formats to capture in IOSpec fields.
            pipeline_ref_domain: Optional domain name for the pipeline.
            pipeline_ref_main_pipe: Optional main pipe name.

        Returns:
            Initial GraphContext to pass through JobMetadata.

        Raises:
            ValueError: If a tracer for this graph_id already exists.
        """
        if graph_id in self._tracers:
            msg = f"Tracer for graph '{graph_id}' already exists"
            raise ValueError(msg)

        tracer = GraphTracer()
        self._tracers[graph_id] = tracer

        return tracer.setup(
            graph_id=graph_id,
            data_inclusion=data_inclusion,
            pipeline_ref_domain=pipeline_ref_domain,
            pipeline_ref_main_pipe=pipeline_ref_main_pipe,
        )

    def close_tracer(self, graph_id: str) -> GraphSpec | None:
        """Finalize tracing for a specific pipeline run and return its GraphSpec.

        Args:
            graph_id: The graph/pipeline run identifier.

        Returns:
            The completed GraphSpec, or None if no tracer found for this graph_id.
        """
        tracer = self._tracers.pop(graph_id, None)
        if tracer is None:
            return None
        return tracer.teardown()

    def get_tracer(self, graph_id: str) -> GraphTracer | None:
        """Get the tracer for a specific graph_id.

        Args:
            graph_id: The graph/pipeline run identifier.

        Returns:
            The tracer if found, None otherwise.
        """
        return self._get_tracer(graph_id)

    ############################################################
    # Manager lifecycle
    ############################################################

    def setup(self) -> None:
        """Initialize the manager, clearing all existing tracers."""
        self._tracers.clear()

    def teardown(self) -> None:
        """Teardown all tracers and clear internal state."""
        # Teardown each active tracer
        for tracer in self._tracers.values():
            tracer.teardown()
        self._tracers.clear()

    ############################################################
    # Tracing events (routed to appropriate tracer)
    ############################################################

    def on_pipe_start(
        self,
        graph_context: GraphContext,
        pipe_code: str,
        pipe_type: str,
        node_kind: NodeKind,
        started_at: datetime,
        input_specs: list[IOSpec] | None = None,
    ) -> tuple[str | None, GraphContext | None]:
        """Record the start of a pipe execution.

        Args:
            graph_context: Current graph context containing graph_id.
            pipe_code: The pipe code being executed.
            pipe_type: The pipe type (e.g., "PipeLLM", "PipeSequence").
            node_kind: The kind of node (controller, operator, etc.).
            started_at: When the pipe started executing.
            input_specs: Optional list of IOSpec describing the inputs consumed.

        Returns:
            Tuple of (node_id, child_graph_context) if tracing is active, (None, None) otherwise.
        """
        tracer = self._get_tracer(graph_context.graph_id)
        if tracer is None:
            return None, None

        return tracer.on_pipe_start(
            graph_context=graph_context,
            pipe_code=pipe_code,
            pipe_type=pipe_type,
            node_kind=node_kind,
            started_at=started_at,
            input_specs=input_specs,
        )

    def on_pipe_end_success(
        self,
        graph_id: str,
        node_id: str | None,
        ended_at: datetime,
        output_preview: str | None = None,
        metrics: dict[str, float] | None = None,
        output_spec: IOSpec | None = None,
    ) -> None:
        """Record successful completion of a pipe execution.

        Args:
            graph_id: The graph identifier.
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe finished executing.
            output_preview: Optional truncated preview of the output.
            metrics: Optional metrics (e.g., token counts).
            output_spec: Optional IOSpec describing the output produced.
        """
        if node_id is None:
            return

        tracer = self._get_tracer(graph_id)
        if tracer is None:
            return

        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=ended_at,
            output_preview=output_preview,
            metrics=metrics,
            output_spec=output_spec,
        )

    def on_pipe_end_error(
        self,
        graph_id: str,
        node_id: str | None,
        ended_at: datetime,
        error_type: str,
        error_message: str,
        error_stack: str | None = None,
    ) -> None:
        """Record failed completion of a pipe execution.

        Args:
            graph_id: The graph identifier.
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe failed.
            error_type: The exception type name.
            error_message: The error message.
            error_stack: Optional stack trace.
        """
        if node_id is None:
            return

        tracer = self._get_tracer(graph_id)
        if tracer is None:
            return

        tracer.on_pipe_end_error(
            node_id=node_id,
            ended_at=ended_at,
            error_type=error_type,
            error_message=error_message,
            error_stack=error_stack,
        )

    def add_edge(
        self,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
    ) -> None:
        """Add an edge between two nodes.

        Args:
            graph_id: The graph identifier.
            source_node_id: The source node ID.
            target_node_id: The target node ID.
            edge_kind: The type of edge.
            label: Optional label for the edge.
        """
        tracer = self._get_tracer(graph_id)
        if tracer is None:
            return

        tracer.add_edge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_kind=edge_kind,
            label=label,
        )
