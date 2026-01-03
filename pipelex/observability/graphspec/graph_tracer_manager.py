"""Graph tracer manager with singleton pattern for access from PipeAbstract without hub imports."""

from datetime import datetime
from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.observability.graphspec.graph_context import GraphContext
from pipelex.observability.graphspec.graph_tracer_protocol import GraphTracerProtocol
from pipelex.observability.graphspec.graphspec import EdgeKind, GraphSpec, NodeKind
from pipelex.system.registries.singleton import ABCSingletonMeta, MetaSingleton

if TYPE_CHECKING:
    from pipelex.observability.graphspec.graph_tracer import GraphTracer

# Re-export NodeKind for use by pipe_abstract without additional imports
__all__ = ["GraphTracerManager", "GraphTracerManagerAbstract", "NodeKind"]


class GraphTracerManagerAbstract(metaclass=ABCSingletonMeta):
    """Abstract singleton manager for graph tracing.

    This provides a way to access the graph tracer without importing from hub,
    avoiding circular dependency issues (similar to TelemetryManagerAbstract).
    """

    @classmethod
    def clear_instance(cls) -> None:
        """Clear the singleton instance from MetaSingleton registry."""
        MetaSingleton.clear_subclass_instances(GraphTracerManagerAbstract)

    @classmethod
    def get_instance(cls) -> "GraphTracerManagerAbstract | None":
        """Get the singleton instance from MetaSingleton registry.

        This provides a way to access the graph tracer manager without importing from hub,
        avoiding circular dependency issues.
        """
        return MetaSingleton.get_subclass_instance(GraphTracerManagerAbstract)  # type: ignore[type-abstract]

    @classmethod
    def get_instance_tracer(cls) -> GraphTracerProtocol | None:
        """Get the graph tracer from the singleton instance.

        This provides a way to access the tracer without importing from hub,
        avoiding circular dependency issues.
        """
        instance = cls.get_instance()
        if instance is None:
            return None
        return instance.get_tracer()

    def get_tracer(self) -> GraphTracerProtocol | None:
        """Get the graph tracer. Override in concrete class."""
        return None

    def on_pipe_start(
        self,
        graph_context: GraphContext,
        pipe_code: str,
        pipe_type: str,
        node_kind: NodeKind,
        started_at: datetime,
    ) -> tuple[str | None, GraphContext | None]:
        """Record the start of a pipe execution.

        Returns:
            Tuple of (node_id, child_graph_context) if tracing is active, (None, None) otherwise.
        """
        tracer = self.get_tracer()
        if tracer is None:
            return None, None
        return tracer.on_pipe_start(
            graph_context=graph_context,
            pipe_code=pipe_code,
            pipe_type=pipe_type,
            node_kind=node_kind,
            started_at=started_at,
        )

    def on_pipe_end_success(
        self,
        node_id: str | None,
        ended_at: datetime,
        output_preview: str | None = None,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """Record successful completion of a pipe execution."""
        if node_id is None:
            return
        tracer = self.get_tracer()
        if tracer is None:
            return
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=ended_at,
            output_preview=output_preview,
            metrics=metrics,
        )

    def on_pipe_end_error(
        self,
        node_id: str | None,
        ended_at: datetime,
        error_type: str,
        error_message: str,
        error_stack: str | None = None,
    ) -> None:
        """Record failed completion of a pipe execution."""
        if node_id is None:
            return
        tracer = self.get_tracer()
        if tracer is None:
            return
        tracer.on_pipe_end_error(
            node_id=node_id,
            ended_at=ended_at,
            error_type=error_type,
            error_message=error_message,
            error_stack=error_stack,
        )


class GraphTracerManager(GraphTracerManagerAbstract):
    """Concrete implementation of the graph tracer manager."""

    def __init__(self, tracer: "GraphTracer") -> None:
        self._tracer = tracer

    @override
    def get_tracer(self) -> GraphTracerProtocol:
        return self._tracer

    def setup(
        self,
        graph_id: str,
        pipeline_ref_domain: str | None = None,
        pipeline_ref_main_pipe: str | None = None,
    ) -> GraphContext:
        """Initialize tracing for a new pipeline run."""
        return self._tracer.setup(
            graph_id=graph_id,
            pipeline_ref_domain=pipeline_ref_domain,
            pipeline_ref_main_pipe=pipeline_ref_main_pipe,
        )

    def teardown(self) -> GraphSpec | None:
        """Finalize tracing and return the built GraphSpec."""
        result = self._tracer.teardown()
        # Clear the singleton so it can be re-created for the next run
        GraphTracerManagerAbstract.clear_instance()
        return result

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
    ) -> None:
        """Add an edge between two nodes."""
        self._tracer.add_edge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_kind=edge_kind,
            label=label,
        )
