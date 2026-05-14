"""Graph tracer manager with singleton pattern for access from PipeAbstract without hub imports."""

from datetime import datetime
from typing import Any

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graph_tracer_protocol import GraphTracerProtocol
from pipelex.graph.graphspec import EdgeKind, GraphSpec, IOSpec, NodeKind
from pipelex.system.registries.singleton import ABCSingletonMeta, MetaSingleton
from pipelex.tracing.event_log_protocol import EventLogProtocol  # noqa: TC001 - used in open_tracer signature


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
    def get_instance_tracer(cls, lookup_key: str) -> GraphTracerProtocol | None:
        """Get the graph tracer for a specific lookup key from the singleton instance.

        This provides a way to access the tracer without importing from hub,
        avoiding circular dependency issues.

        Args:
            lookup_key: The tracer lookup key (graph_id or tracer_key).

        Returns:
            The tracer for the given key, or None if not found.
        """
        instance = cls.get_instance()
        if instance is None:
            return None
        return instance.get_tracer(lookup_key)

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
        event_log: "EventLogProtocol | None" = None,
        workflow_id: str = "direct",
        pipeline_run_id: str | None = None,
        tracer_key: str | None = None,
    ) -> GraphContext:
        """Create and initialize a new tracer for a pipeline run.

        Args:
            graph_id: Unique identifier for this pipeline run (used in node ID generation).
            data_inclusion: Configuration controlling which data formats to capture in IOSpec fields.
            pipeline_ref_domain: Optional domain name for the pipeline.
            pipeline_ref_main_pipe: Optional main pipe name.
            event_log: Optional event log for distributed tracing. When set,
                the tracer emits trace events as a side effect alongside in-memory accumulation.
            workflow_id: Temporal workflow ID or "direct" for single-process mode.
            pipeline_run_id: Pipeline run ID for event emission.
            tracer_key: Lookup key for the tracer in the manager's dict. Defaults to graph_id.
                In Temporal mode, use the workflow_id to avoid collisions when multiple
                workflows share the same graph_id on the same process.

        Returns:
            Initial GraphContext to pass through JobMetadata.

        Raises:
            ValueError: If a tracer for this key already exists.
        """
        key = tracer_key or graph_id
        if key in self._tracers:
            msg = f"Tracer for key '{key}' already exists"
            raise ValueError(msg)

        tracer = GraphTracer()
        self._tracers[key] = tracer

        graph_context = tracer.setup(
            graph_id=graph_id,
            data_inclusion=data_inclusion,
            pipeline_ref_domain=pipeline_ref_domain,
            pipeline_ref_main_pipe=pipeline_ref_main_pipe,
            event_log=event_log,
            workflow_id=workflow_id,
            pipeline_run_id=pipeline_run_id,
        )
        # Set the tracer_key on the GraphContext so downstream lookups use the same key
        if tracer_key is not None:
            graph_context = graph_context.model_copy(update={"tracer_key": tracer_key})
        return graph_context

    def close_tracer(self, tracer_key: str) -> GraphSpec | None:
        """Finalize tracing for a specific pipeline run and return its GraphSpec.

        Args:
            tracer_key: The tracer lookup key (graph_id or workflow_id).

        Returns:
            The completed GraphSpec, or None if no tracer found for this key.
        """
        tracer = self._tracers.pop(tracer_key, None)
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
        pipe_data: dict[str, Any] | None = None,
        concept_data: list[dict[str, Any]] | None = None,
        description: str | None = None,
        domain_code: str | None = None,
    ) -> tuple[str | None, GraphContext | None]:
        """Record the start of a pipe execution.

        Args:
            graph_context: Current graph context containing graph_id.
            pipe_code: The pipe code being executed.
            pipe_type: The pipe type (e.g., "PipeLLM", "PipeSequence").
            node_kind: The kind of node (controller, operator, etc.).
            started_at: When the pipe started executing.
            input_specs: Optional list of IOSpec describing the inputs consumed.
            pipe_data: Optional serialized pipe instance for the pipe registry.
            concept_data: Optional list of serialized concept dicts for the concept registry.
            description: Optional human-readable pipe description (mirrored onto NodeSpec).
            domain_code: Optional domain code of the pipe (mirrored onto NodeSpec).

        Returns:
            Tuple of (node_id, child_graph_context) if tracing is active, (None, None) otherwise.
        """
        tracer = self._get_tracer(graph_context.lookup_key)
        if tracer is None:
            return None, None

        return tracer.on_pipe_start(
            graph_context=graph_context,
            pipe_code=pipe_code,
            pipe_type=pipe_type,
            node_kind=node_kind,
            started_at=started_at,
            input_specs=input_specs,
            pipe_data=pipe_data,
            concept_data=concept_data,
            description=description,
            domain_code=domain_code,
        )

    def on_pipe_end_success(
        self,
        lookup_key: str,
        node_id: str | None,
        ended_at: datetime,
        output_preview: str | None = None,
        metrics: dict[str, float] | None = None,
        output_spec: IOSpec | None = None,
        output_concept_data: dict[str, Any] | None = None,
    ) -> None:
        """Record successful completion of a pipe execution.

        Args:
            lookup_key: The tracer lookup key.
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe finished executing.
            output_preview: Optional truncated preview of the output.
            metrics: Optional metrics (e.g., token counts).
            output_spec: Optional IOSpec describing the output produced.
            output_concept_data: Optional serialized concept dict for the actual output concept.
        """
        if node_id is None:
            return

        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return

        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=ended_at,
            output_preview=output_preview,
            metrics=metrics,
            output_spec=output_spec,
            output_concept_data=output_concept_data,
        )

    def register_execution_data(
        self,
        lookup_key: str,
        node_id: str | None,
        execution_data: dict[str, Any],
    ) -> None:
        """Register execution metadata for a node.

        Args:
            lookup_key: The tracer lookup key (graph_id or workflow_id).
            node_id: The node ID to attach execution data to.
            execution_data: Dictionary of execution metadata.
        """
        if node_id is None:
            return
        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return
        tracer.register_execution_data(node_id=node_id, execution_data=execution_data)

    def on_pipe_end_error(
        self,
        lookup_key: str,
        node_id: str | None,
        ended_at: datetime,
        error_type: str,
        error_message: str,
        error_stack: str | None = None,
    ) -> None:
        """Record failed completion of a pipe execution.

        Args:
            lookup_key: The tracer lookup key.
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe failed.
            error_type: The exception type name.
            error_message: The error message.
            error_stack: Optional stack trace.
        """
        if node_id is None:
            return

        tracer = self._get_tracer(lookup_key)
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
        lookup_key: str,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
    ) -> None:
        """Add an edge between two nodes.

        Args:
            lookup_key: The tracer lookup key.
            source_node_id: The source node ID.
            target_node_id: The target node ID.
            edge_kind: The type of edge.
            label: Optional label for the edge.
        """
        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return

        tracer.add_edge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_kind=edge_kind,
            label=label,
        )

    def register_controller_output(
        self,
        lookup_key: str,
        node_id: str,
        output_spec: IOSpec,
    ) -> None:
        """Register an additional output for a controller node.

        Args:
            lookup_key: The tracer lookup key.
            node_id: The controller node ID.
            output_spec: The IOSpec describing the output.
        """
        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return
        tracer.register_controller_output(
            node_id=node_id,
            output_spec=output_spec,
        )

    def register_batch_item_extraction(
        self,
        lookup_key: str,
        list_stuff_code: str,
        item_stuff_code: str,
        item_index: int,
        batch_controller_node_id: str | None = None,
    ) -> None:
        """Register that a list stuff produced an item stuff during batch iteration.

        Args:
            lookup_key: The tracer lookup key.
            list_stuff_code: The stuff_code of the input list.
            item_stuff_code: The stuff_code of the extracted item.
            item_index: The index of the item in the list.
            batch_controller_node_id: The node_id of the PipeBatch controller performing the fan-out.
                If provided, this will be used as the source node for BATCH_ITEM edges in controller-centric mode.
        """
        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return
        tracer.register_batch_item_extraction(
            list_stuff_code=list_stuff_code,
            item_stuff_code=item_stuff_code,
            item_index=item_index,
            batch_controller_node_id=batch_controller_node_id,
        )

    def register_batch_aggregation(
        self,
        lookup_key: str,
        output_list_stuff_code: str,
        item_stuff_code: str,
        item_index: int,
        batch_controller_node_id: str | None = None,
    ) -> None:
        """Register that an item stuff will be aggregated into an output list.

        Args:
            lookup_key: The tracer lookup key.
            output_list_stuff_code: The stuff_code of the output list.
            item_stuff_code: The stuff_code of the item to aggregate.
            item_index: The index of the item in the output list.
            batch_controller_node_id: The node_id of the PipeBatch controller that will produce the output list.
                If provided, this will be used as the target node for BATCH_AGGREGATE edges.
        """
        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return
        tracer.register_batch_aggregation(
            output_list_stuff_code=output_list_stuff_code,
            item_stuff_code=item_stuff_code,
            item_index=item_index,
            batch_controller_node_id=batch_controller_node_id,
        )

    def register_parallel_combine(
        self,
        lookup_key: str,
        combined_stuff_code: str,
        branch_stuff_codes: list[str],
        parallel_controller_node_id: str,
    ) -> None:
        """Register that branch outputs are combined into a single output in PipeParallel.

        Args:
            lookup_key: The tracer lookup key.
            combined_stuff_code: The stuff_code of the combined output.
            branch_stuff_codes: The stuff_codes of the individual branch outputs.
            parallel_controller_node_id: The node_id of the PipeParallel controller.
        """
        tracer = self._get_tracer(lookup_key)
        if tracer is None:
            return
        tracer.register_parallel_combine(
            combined_stuff_code=combined_stuff_code,
            branch_stuff_codes=branch_stuff_codes,
            parallel_controller_node_id=parallel_controller_node_id,
        )
