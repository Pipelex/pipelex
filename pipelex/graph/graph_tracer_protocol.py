from datetime import datetime
from typing import Any, Protocol

from typing_extensions import override

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graphspec import EdgeKind, GraphSpec, IOSpec, NodeKind
from pipelex.tracing.event_log_protocol import EventLogProtocol  # noqa: TC001 - used in setup signature


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
        event_log: "EventLogProtocol | None" = None,
        workflow_id: str = "direct",
        pipeline_run_id: str | None = None,
    ) -> GraphContext:
        """Initialize tracing for a new pipeline run.

        Args:
            graph_id: Unique identifier for this execution graph.
            data_inclusion: Configuration controlling which data formats to capture in IOSpec fields.
            pipeline_ref_domain: Optional domain name for the pipeline.
            pipeline_ref_main_pipe: Optional main pipe name.
            event_log: Optional event log for distributed tracing.
            workflow_id: Temporal workflow ID or "direct" for single-process mode.
            pipeline_run_id: Pipeline run ID for event emission.

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
        pipe_data: dict[str, Any] | None = None,
        concept_data: list[dict[str, Any]] | None = None,
        description: str | None = None,
        domain_code: str | None = None,
    ) -> tuple[str, GraphContext]:
        """Record the start of a pipe execution.

        Args:
            graph_context: Current graph context from JobMetadata.
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
        output_concept_data: dict[str, Any] | None = None,
    ) -> None:
        """Record successful completion of a pipe execution.

        Args:
            node_id: The node ID returned from on_pipe_start.
            ended_at: When the pipe finished executing.
            output_preview: Optional truncated preview of the output.
            metrics: Optional metrics (e.g., token counts).
            output_spec: Optional IOSpec describing the output produced.
            output_concept_data: Optional serialized concept dict for the actual output concept.
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
        source_stuff_digest: str | None = None,
        target_stuff_digest: str | None = None,
    ) -> None:
        """Add an edge between two nodes.

        Args:
            source_node_id: The source node ID.
            target_node_id: The target node ID.
            edge_kind: The type of edge.
            label: Optional label for the edge.
            source_stuff_digest: Optional stuff digest for the source (for batch edges).
            target_stuff_digest: Optional stuff digest for the target (for batch edges).
        """
        ...

    def register_controller_output(
        self,
        node_id: str,
        output_spec: IOSpec,
    ) -> None:
        """Register an additional output for a controller node.

        This allows controllers like PipeParallel to explicitly register their
        branch outputs so that DATA edges flow from the controller to downstream consumers.

        Args:
            node_id: The controller node ID.
            output_spec: The IOSpec describing the output.
        """
        ...

    def register_batch_item_extraction(
        self,
        list_stuff_code: str,
        item_stuff_code: str,
        item_index: int,
        batch_controller_node_id: str | None = None,
    ) -> None:
        """Register that a list stuff produced an item stuff during batch iteration.

        Args:
            list_stuff_code: The stuff_code of the input list.
            item_stuff_code: The stuff_code of the extracted item.
            item_index: The index of the item in the list.
            batch_controller_node_id: The node_id of the PipeBatch controller performing the fan-out.
                If provided, this will be used as the source node for BATCH_ITEM edges in controller-centric mode.
        """
        ...

    def register_batch_aggregation(
        self,
        output_list_stuff_code: str,
        item_stuff_code: str,
        item_index: int,
        batch_controller_node_id: str | None = None,
    ) -> None:
        """Register that an item stuff will be aggregated into an output list.

        Args:
            output_list_stuff_code: The stuff_code of the output list.
            item_stuff_code: The stuff_code of the item to aggregate.
            item_index: The index of the item in the output list.
            batch_controller_node_id: The node_id of the PipeBatch controller that will produce the output list.
                If provided, this will be used as the target node for BATCH_AGGREGATE edges instead of
                looking up the producer from stuff_producer_map (which may be overwritten by parent controllers).
        """
        ...

    def register_parallel_combine(
        self,
        combined_stuff_code: str,
        branch_stuff_codes: list[str],
        parallel_controller_node_id: str,
    ) -> None:
        """Register that branch outputs are combined into a single output in PipeParallel.

        Creates PARALLEL_COMBINE edges from each branch output stuff node
        to the combined output stuff node.

        Args:
            combined_stuff_code: The stuff_code of the combined output.
            branch_stuff_codes: The stuff_codes of the individual branch outputs.
            parallel_controller_node_id: The node_id of the PipeParallel controller.
        """
        ...

    def register_execution_data(
        self,
        node_id: str,
        execution_data: dict[str, Any],
    ) -> None:
        """Register execution metadata for a node.

        Args:
            node_id: The node ID to attach execution data to.
            execution_data: Dictionary of execution metadata (rendered prompts, resolved models, etc.).
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
        event_log: "EventLogProtocol | None" = None,
        workflow_id: str = "direct",
        pipeline_run_id: str | None = None,
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
        pipe_data: dict[str, Any] | None = None,
        concept_data: list[dict[str, Any]] | None = None,
        description: str | None = None,
        domain_code: str | None = None,
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
        output_concept_data: dict[str, Any] | None = None,
    ) -> None:
        pass

    @override
    def register_execution_data(
        self,
        node_id: str,
        execution_data: dict[str, Any],
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
        source_stuff_digest: str | None = None,
        target_stuff_digest: str | None = None,
    ) -> None:
        pass

    @override
    def register_controller_output(
        self,
        node_id: str,
        output_spec: IOSpec,
    ) -> None:
        pass

    @override
    def register_batch_item_extraction(
        self,
        list_stuff_code: str,
        item_stuff_code: str,
        item_index: int,
        batch_controller_node_id: str | None = None,
    ) -> None:
        pass

    @override
    def register_batch_aggregation(
        self,
        output_list_stuff_code: str,
        item_stuff_code: str,
        item_index: int,
        batch_controller_node_id: str | None = None,
    ) -> None:
        pass

    @override
    def register_parallel_combine(
        self,
        combined_stuff_code: str,
        branch_stuff_codes: list[str],
        parallel_controller_node_id: str,
    ) -> None:
        pass
