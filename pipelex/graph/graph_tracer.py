"""GraphTracer implementation that builds GraphSpec during pipeline execution."""

from datetime import datetime, timezone

from typing_extensions import override

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graph_tracer_protocol import GraphTracerProtocol
from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    ErrorSpec,
    GraphSpec,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
    TimingSpec,
)
from pipelex.tracing.event_log_protocol import EventLogProtocol  # noqa: TC001 - used in __init__ annotations
from pipelex.tracing.trace_events import (
    BatchAggregateEvent,
    BatchItemEvent,
    ControllerOutputEvent,
    EdgeEvent,
    ParallelCombineEvent,
    PipeEndErrorEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
)


class _MutableNodeData:
    """Internal mutable data structure for building a node before finalization."""

    def __init__(
        self,
        node_id: str,
        pipe_code: str,
        pipe_type: str,
        node_kind: NodeKind,
        started_at: datetime,
        parent_node_id: str | None,
        input_specs: list[IOSpec] | None = None,
    ) -> None:
        self.node_id = node_id
        self.pipe_code = pipe_code
        self.pipe_type = pipe_type
        self.node_kind = node_kind
        self.started_at = started_at
        self.parent_node_id = parent_node_id
        self.ended_at: datetime | None = None
        self.status: NodeStatus = NodeStatus.RUNNING
        self.output_preview: str | None = None
        self.metrics: dict[str, float] = {}
        self.error: ErrorSpec | None = None
        self.input_specs: list[IOSpec] = input_specs or []
        self.output_specs: list[IOSpec] = []

    def to_node_spec(self) -> NodeSpec:
        """Convert to immutable NodeSpec."""
        assert self.started_at is not None
        assert self.ended_at is not None
        timing = TimingSpec(
            started_at=self.started_at,
            ended_at=self.ended_at,
        )

        # Build NodeIOSpec from captured input/output specs
        outputs = list(self.output_specs)

        node_io = NodeIOSpec(
            inputs=self.input_specs,
            outputs=outputs,
        )

        return NodeSpec(
            node_id=self.node_id,
            kind=self.node_kind,
            pipe_code=self.pipe_code,
            pipe_type=self.pipe_type,
            status=self.status,
            timing=timing,
            node_io=node_io,
            error=self.error,
            metrics=self.metrics,
        )


class GraphTracer(GraphTracerProtocol):
    """Builds a GraphSpec by accumulating nodes and edges during pipe execution.

    This tracer maintains an in-memory representation of the execution graph
    that can be finalized into a GraphSpec when the pipeline completes.

    Note: This implementation accumulates data in-memory, which works for
    single-process execution. For truly distributed scenarios, consider
    sending events to an external collector.
    """

    def __init__(self) -> None:
        self._is_active: bool = False
        self._graph_id: str | None = None
        self._pipeline_ref: PipelineRef | None = None
        self._created_at: datetime | None = None
        self._nodes: dict[str, _MutableNodeData] = {}
        self._edges: list[EdgeSpec] = []
        self._node_sequence: int = 0
        self._edge_sequence: int = 0
        # Maps stuff_code (digest) to the node_id that produced it
        self._stuff_producer_map: dict[str, str] = {}
        # Maps list_stuff_code -> (batch_controller_node_id, [(item_stuff_code, item_index), ...])
        # The batch_controller_node_id is tracked to ensure BATCH_ITEM edges can source from the correct node
        self._batch_item_map: dict[str, tuple[str | None, list[tuple[str, int]]]] = {}
        # Maps output_list_stuff_code -> (batch_controller_node_id, [(item_stuff_code, item_index), ...])
        # The batch_controller_node_id is tracked to ensure BATCH_AGGREGATE edges target the correct node
        # (the PipeBatch), not a parent controller that may later register as producer of the same stuff
        self._batch_aggregate_map: dict[str, tuple[str | None, list[tuple[str, int]]]] = {}
        # Maps combined_stuff_code -> (parallel_controller_node_id, [(branch_stuff_code, branch_producer_node_id)])
        # Used to create PARALLEL_COMBINE edges from branch outputs to combined output
        # The branch_producer_node_id is snapshotted at registration time, before register_controller_output
        # overrides _stuff_producer_map to point branch stuff codes to the controller node
        self._parallel_combine_map: dict[str, tuple[str, list[tuple[str, str]]]] = {}
        # Event log for distributed tracing (None = no event emission, direct mode)
        self._event_log: EventLogProtocol | None = None
        # "direct" for single-process mode, full Temporal workflow ID otherwise
        self._workflow_id: str = "direct"
        # Pipeline run ID for event emission
        self._pipeline_run_id: str | None = None
        # Per-writer monotonic counter for event sequencing
        self._event_sequence: int = 0

    @property
    def is_active(self) -> bool:
        """Whether tracing is currently active."""
        return self._is_active

    @property
    def _event_pipeline_run_id(self) -> str:
        """Pipeline run ID for event emission, falling back to graph_id."""
        return self._pipeline_run_id or self._graph_id or ""

    def _emit_event(self, event: TraceEvent) -> None:
        """Emit a trace event to the event log.

        Must only be called when self._event_log is not None.
        """
        assert self._event_log is not None
        self._event_log.emit(event)

    def _next_event_sequence(self) -> int:
        """Return the next monotonic sequence number for event emission."""
        seq = self._event_sequence
        self._event_sequence += 1
        return seq

    def _make_node_id(self) -> str:
        """Generate a node ID, including workflow_id when in Temporal mode."""
        if self._workflow_id != "direct":
            node_id = f"{self._graph_id}:{self._workflow_id}:node_{self._node_sequence}"
        else:
            node_id = f"{self._graph_id}:node_{self._node_sequence}"
        self._node_sequence += 1
        return node_id

    def _make_edge_id(self) -> str:
        """Generate an edge ID, including workflow_id when in Temporal mode."""
        if self._workflow_id != "direct":
            edge_id = f"{self._graph_id}:{self._workflow_id}:edge_{self._edge_sequence}"
        else:
            edge_id = f"{self._graph_id}:edge_{self._edge_sequence}"
        self._edge_sequence += 1
        return edge_id

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
        """Initialize tracing for a new pipeline run.

        Args:
            graph_id: Unique identifier for this execution graph.
            data_inclusion: Configuration controlling which data formats to capture.
            pipeline_ref_domain: Optional domain name for the pipeline.
            pipeline_ref_main_pipe: Optional main pipe name.
            event_log: Optional event log for distributed tracing. When set,
                every tracing method emits a TraceEvent as a side effect.
            workflow_id: Temporal workflow ID or "direct" for single-process mode.
                When not "direct", node/edge IDs include the workflow_id segment.
            pipeline_run_id: Pipeline run ID for event emission. Required when event_log is set.
        """
        self._is_active = True
        self._graph_id = graph_id
        self._pipeline_ref = PipelineRef(
            domain=pipeline_ref_domain,
            main_pipe=pipeline_ref_main_pipe,
        )
        self._created_at = datetime.now(timezone.utc)
        self._nodes = {}
        self._edges = []
        self._node_sequence = 0
        self._edge_sequence = 0
        self._stuff_producer_map = {}
        self._batch_item_map = {}
        self._batch_aggregate_map = {}
        self._parallel_combine_map = {}
        self._event_log = event_log
        self._workflow_id = workflow_id
        self._pipeline_run_id = pipeline_run_id
        self._event_sequence = 0

        return GraphContext(
            graph_id=graph_id,
            parent_node_id=None,
            node_sequence=0,
            data_inclusion=data_inclusion,
        )

    @override
    def teardown(self) -> GraphSpec | None:
        """Finalize tracing and return the built GraphSpec."""
        if not self._is_active:
            return None

        # Mark any still-running nodes as canceled (shouldn't happen in normal flow)
        for node_data in self._nodes.values():
            if node_data.status == NodeStatus.RUNNING:
                node_data.status = NodeStatus.CANCELED
                node_data.ended_at = datetime.now(timezone.utc)

        # Generate DATA edges by correlating input stuff_codes with producer nodes
        # (must happen before setting _is_active = False since add_edge checks it)
        self._generate_data_edges()
        self._generate_batch_item_edges()
        self._generate_batch_aggregate_edges()
        self._generate_parallel_combine_edges()

        self._is_active = False

        # Build the final GraphSpec
        nodes = [node_data.to_node_spec() for node_data in self._nodes.values()]

        graph = GraphSpec(
            graph_id=self._graph_id or "unknown",
            created_at=self._created_at or datetime.now(timezone.utc),
            pipeline_ref=self._pipeline_ref or PipelineRef(),
            nodes=nodes,
            edges=self._edges,
        )

        # Reset internal state
        self._graph_id = None
        self._pipeline_ref = None
        self._created_at = None
        self._nodes = {}
        self._edges = []
        self._stuff_producer_map = {}
        self._batch_item_map = {}
        self._batch_aggregate_map = {}
        self._parallel_combine_map = {}
        if self._event_log is not None:
            self._event_log.close()
        self._event_log = None
        self._workflow_id = "direct"
        self._pipeline_run_id = None
        self._event_sequence = 0

        return graph

    def _generate_data_edges(self) -> None:
        """Generate DATA edges by correlating input stuff_codes with producer nodes.

        For each node's input with a digest (stuff_code), find the node that
        produced that stuff and create a DATA edge from producer to consumer.
        """
        for consumer_node_id, node_data in self._nodes.items():
            for input_spec in node_data.input_specs:
                if input_spec.digest is None:
                    continue
                producer_node_id = self._stuff_producer_map.get(input_spec.digest)
                if producer_node_id is None:
                    # No known producer (may be initial input to pipeline)
                    continue
                if producer_node_id == consumer_node_id:
                    # Don't create self-loops
                    continue
                # Create DATA edge: producer → consumer, labeled with the stuff name
                self.add_edge(
                    source_node_id=producer_node_id,
                    target_node_id=consumer_node_id,
                    edge_kind=EdgeKind.DATA,
                    label=input_spec.name,
                )

    def _generate_batch_item_edges(self) -> None:
        """Generate BATCH_ITEM edges for batch fan-out.

        For each registered batch item extraction, create BATCH_ITEM edges.
        The edge connects:
        - Source: the batch controller node (if provided) or the list producer
        - Target: the branch pipe that consumes the extracted item

        The source/target stuff digests are preserved for the JS renderer to use
        when connecting stuff nodes directly in data-centric mode.
        """
        for list_stuff_code, (batch_controller_node_id, item_entries) in self._batch_item_map.items():
            # Determine source node: prefer batch controller, fall back to list producer
            list_producer_node_id = self._stuff_producer_map.get(list_stuff_code)
            source_node_id = batch_controller_node_id or list_producer_node_id

            if not source_node_id:
                # Try to find a consumer of the list (legacy fallback)
                for node_id, node_data in self._nodes.items():
                    for input_spec in node_data.input_specs:
                        if input_spec.digest == list_stuff_code:
                            source_node_id = node_id
                            break
                    if source_node_id:
                        break

            if not source_node_id:
                continue

            for item_stuff_code, item_index in item_entries:
                # Find consumer nodes for this item (the branch pipes)
                for consumer_node_id, node_data in self._nodes.items():
                    for input_spec in node_data.input_specs:
                        if input_spec.digest == item_stuff_code:
                            if source_node_id != consumer_node_id:
                                self.add_edge(
                                    source_node_id=source_node_id,
                                    target_node_id=consumer_node_id,
                                    edge_kind=EdgeKind.BATCH_ITEM,
                                    label=f"[{item_index}]",
                                    source_stuff_digest=list_stuff_code,
                                    target_stuff_digest=item_stuff_code,
                                )
                            break

    def _generate_batch_aggregate_edges(self) -> None:
        """Generate BATCH_AGGREGATE edges from item producers to output list producer.

        For each registered batch aggregation, create edges from the branch pipe
        outputs to the PipeBatch node that produces the aggregated list.

        The target node is determined as follows:
        1. If batch_controller_node_id was provided during registration, use that
        2. Otherwise, fall back to looking up the producer from _stuff_producer_map

        The explicit batch_controller_node_id is preferred because the _stuff_producer_map
        may be overwritten when a parent controller (e.g., PipeSequence) finishes after
        the PipeBatch and registers the same output stuff as its own output.
        """
        for output_list_stuff_code, (batch_controller_node_id, item_entries) in self._batch_aggregate_map.items():
            # Determine the target node for aggregate edges
            # Prefer the explicitly tracked batch controller node_id if available
            target_node_id = batch_controller_node_id or self._stuff_producer_map.get(output_list_stuff_code)
            if not target_node_id:
                continue

            for item_stuff_code, item_index in item_entries:
                # Find the producer of this item (the branch pipe)
                item_producer_id = self._stuff_producer_map.get(item_stuff_code)
                if item_producer_id and item_producer_id != target_node_id:
                    self.add_edge(
                        source_node_id=item_producer_id,
                        target_node_id=target_node_id,
                        edge_kind=EdgeKind.BATCH_AGGREGATE,
                        label=f"[{item_index}]",
                        source_stuff_digest=item_stuff_code,
                        target_stuff_digest=output_list_stuff_code,
                    )

    def _generate_parallel_combine_edges(self) -> None:
        """Generate PARALLEL_COMBINE edges from branch output stuff nodes to the combined output stuff node.

        For each registered parallel combine, create edges from each branch output
        to the combined output, showing how individual branch results are merged.

        Uses snapshotted branch producer node IDs captured during register_parallel_combine,
        before register_controller_output overrides _stuff_producer_map.
        """
        for combined_stuff_code, (parallel_controller_node_id, branch_entries) in self._parallel_combine_map.items():
            for branch_stuff_code, branch_producer_id in branch_entries:
                if branch_producer_id != parallel_controller_node_id:
                    self.add_edge(
                        source_node_id=branch_producer_id,
                        target_node_id=parallel_controller_node_id,
                        edge_kind=EdgeKind.PARALLEL_COMBINE,
                        source_stuff_digest=branch_stuff_code,
                        target_stuff_digest=combined_stuff_code,
                    )

    @override
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
        if not self._is_active:
            return
        if list_stuff_code not in self._batch_item_map:
            self._batch_item_map[list_stuff_code] = (batch_controller_node_id, [])
        # Unpack tuple to append to the item list (tuples are immutable, but the contained list is mutable)
        _existing_controller_id, item_list = self._batch_item_map[list_stuff_code]
        item_list.append((item_stuff_code, item_index))
        # Note: We keep the first batch_controller_node_id registered for this list
        # (all items for the same input list should come from the same batch controller)

        # Emit BatchItemEvent
        if self._event_log is not None:
            self._emit_event(
                BatchItemEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=datetime.now(timezone.utc),
                    sequence=self._next_event_sequence(),
                    list_stuff_code=list_stuff_code,
                    item_stuff_code=item_stuff_code,
                    item_index=item_index,
                    batch_controller_node_id=batch_controller_node_id or "",
                )
            )

    @override
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
                If provided, this will be used as the target node for BATCH_AGGREGATE edges.
        """
        if not self._is_active:
            return
        if output_list_stuff_code not in self._batch_aggregate_map:
            self._batch_aggregate_map[output_list_stuff_code] = (batch_controller_node_id, [])
        # Unpack tuple to append to the item list (tuples are immutable, but the contained list is mutable)
        _existing_controller_id, item_list = self._batch_aggregate_map[output_list_stuff_code]
        item_list.append((item_stuff_code, item_index))
        # Note: We keep the first batch_controller_node_id registered for this output list
        # (all items for the same output list should come from the same batch controller)

        # Emit BatchAggregateEvent
        if self._event_log is not None:
            self._emit_event(
                BatchAggregateEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=datetime.now(timezone.utc),
                    sequence=self._next_event_sequence(),
                    output_list_stuff_code=output_list_stuff_code,
                    item_stuff_code=item_stuff_code,
                    item_index=item_index,
                    batch_controller_node_id=batch_controller_node_id or "",
                )
            )

    @override
    def register_parallel_combine(
        self,
        combined_stuff_code: str,
        branch_stuff_codes: list[str],
        parallel_controller_node_id: str,
    ) -> None:
        """Register that branch outputs are combined into a single output in PipeParallel.

        Args:
            combined_stuff_code: The stuff_code of the combined output.
            branch_stuff_codes: The stuff_codes of the individual branch outputs.
            parallel_controller_node_id: The node_id of the PipeParallel controller.
        """
        if not self._is_active:
            return
        # Snapshot the current branch producers from _stuff_producer_map before
        # register_controller_output overrides them to point to the controller node.
        # This must be called BEFORE _register_branch_outputs_with_graph_tracer.
        branch_entries: list[tuple[str, str]] = []
        for branch_code in branch_stuff_codes:
            producer_id = self._stuff_producer_map.get(branch_code)
            if producer_id:
                branch_entries.append((branch_code, producer_id))
        self._parallel_combine_map[combined_stuff_code] = (parallel_controller_node_id, branch_entries)

        # Emit ParallelCombineEvent with snapshotted producer IDs
        if self._event_log is not None:
            self._emit_event(
                ParallelCombineEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=datetime.now(timezone.utc),
                    sequence=self._next_event_sequence(),
                    combined_stuff_code=combined_stuff_code,
                    branch_stuff_codes=branch_stuff_codes,
                    parallel_controller_node_id=parallel_controller_node_id,
                    branch_producer_node_ids=branch_entries,
                )
            )

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
        """Record the start of a pipe execution."""
        if not self._is_active:
            # Return dummy values when not active
            node_id = graph_context.make_node_id()
            child_context = graph_context.copy_for_child(node_id, graph_context.node_sequence + 1)
            return node_id, child_context

        # Generate node ID (includes workflow_id in Temporal mode)
        node_id = self._make_node_id()

        # Create mutable node data
        node_data = _MutableNodeData(
            node_id=node_id,
            pipe_code=pipe_code,
            pipe_type=pipe_type,
            node_kind=node_kind,
            started_at=started_at,
            parent_node_id=graph_context.parent_node_id,
            input_specs=input_specs,
        )
        self._nodes[node_id] = node_data

        # Emit PipeStartEvent
        if self._event_log is not None:
            self._emit_event(
                PipeStartEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=started_at,
                    sequence=self._next_event_sequence(),
                    node_id=node_id,
                    parent_node_id=graph_context.parent_node_id,
                    pipe_code=pipe_code,
                    pipe_type=pipe_type,
                    node_kind=node_kind,
                    input_specs=input_specs or [],
                )
            )

        # Add containment edge from parent if this is a child pipe
        if graph_context.parent_node_id is not None:
            self.add_edge(
                source_node_id=graph_context.parent_node_id,
                target_node_id=node_id,
                edge_kind=EdgeKind.CONTAINS,
            )

        # Create child context - use copy_for_child to preserve include_full_data
        child_context = graph_context.copy_for_child(
            child_node_id=node_id,
            next_sequence=self._node_sequence,
        )

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
        """Record successful completion of a pipe execution."""
        if not self._is_active:
            return

        node_data = self._nodes.get(node_id)
        if node_data is None:
            return

        node_data.ended_at = ended_at
        node_data.status = NodeStatus.SUCCEEDED
        node_data.output_preview = output_preview
        if metrics:
            node_data.metrics = metrics

        # Store output spec and register in producer map for data flow tracking
        if output_spec is not None:
            # Skip pass-through outputs: if the output digest matches one of the node's
            # input digests, the output is just the unchanged input flowing through
            # (e.g., PipeParallel with add_each_output where main_stuff is the original input)
            input_digests = {spec.digest for spec in node_data.input_specs if spec.digest is not None}
            if output_spec.digest in input_digests:
                # Pass-through: don't register as output or producer
                pass
            else:
                node_data.output_specs.append(output_spec)
                # Register this node as the producer of this stuff_code (digest)
                if output_spec.digest:
                    self._stuff_producer_map[output_spec.digest] = node_id

        # Emit PipeEndSuccessEvent
        if self._event_log is not None:
            self._emit_event(
                PipeEndSuccessEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=ended_at,
                    sequence=self._next_event_sequence(),
                    node_id=node_id,
                    ended_at=ended_at,
                    output_spec=output_spec,
                    metrics=metrics or {},
                )
            )

    @override
    def register_controller_output(
        self,
        node_id: str,
        output_spec: IOSpec,
    ) -> None:
        """Register an additional output for a controller node.

        This allows controllers like PipeParallel to explicitly register their
        branch outputs, overriding sub-pipe registrations in _stuff_producer_map
        so that DATA edges flow from the controller to downstream consumers.

        Args:
            node_id: The controller node ID.
            output_spec: The IOSpec describing the output.
        """
        if not self._is_active:
            return

        node_data = self._nodes.get(node_id)
        if node_data is None:
            return

        node_data.output_specs.append(output_spec)
        if output_spec.digest:
            self._stuff_producer_map[output_spec.digest] = node_id

        # Emit ControllerOutputEvent
        if self._event_log is not None:
            self._emit_event(
                ControllerOutputEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=datetime.now(timezone.utc),
                    sequence=self._next_event_sequence(),
                    node_id=node_id,
                    output_spec=output_spec,
                )
            )

    @override
    def on_pipe_end_error(
        self,
        node_id: str,
        ended_at: datetime,
        error_type: str,
        error_message: str,
        error_stack: str | None = None,
    ) -> None:
        """Record failed completion of a pipe execution."""
        if not self._is_active:
            return

        node_data = self._nodes.get(node_id)
        if node_data is None:
            return

        node_data.ended_at = ended_at
        node_data.status = NodeStatus.FAILED
        error = ErrorSpec(
            error_type=error_type,
            message=error_message,
            stack=error_stack,
        )
        node_data.error = error

        # Emit PipeEndErrorEvent
        if self._event_log is not None:
            self._emit_event(
                PipeEndErrorEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=ended_at,
                    sequence=self._next_event_sequence(),
                    node_id=node_id,
                    ended_at=ended_at,
                    error=error,
                )
            )

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
        """Add an edge between two nodes."""
        if not self._is_active:
            return

        edge_id = self._make_edge_id()

        edge = EdgeSpec(
            edge_id=edge_id,
            source=source_node_id,
            target=target_node_id,
            kind=edge_kind,
            label=label,
            source_stuff_digest=source_stuff_digest,
            target_stuff_digest=target_stuff_digest,
        )
        self._edges.append(edge)

        # Emit EdgeEvent
        if self._event_log is not None:
            self._emit_event(
                EdgeEvent(
                    pipeline_run_id=self._event_pipeline_run_id,
                    workflow_id=self._workflow_id,
                    timestamp=datetime.now(timezone.utc),
                    sequence=self._next_event_sequence(),
                    edge_id=edge_id,
                    source_node_id=source_node_id,
                    target_node_id=target_node_id,
                    edge_kind=edge_kind,
                    label=label,
                    source_stuff_digest=source_stuff_digest,
                    target_stuff_digest=target_stuff_digest,
                )
            )

    def add_selected_outcome_edge(
        self,
        condition_node_id: str,
        outcome_node_id: str,
        outcome_value: str,
    ) -> None:
        """Add an edge indicating a selected condition outcome.

        Args:
            condition_node_id: The condition pipe's node ID.
            outcome_node_id: The selected outcome pipe's node ID.
            outcome_value: The value that was selected.
        """
        self.add_edge(
            source_node_id=condition_node_id,
            target_node_id=outcome_node_id,
            edge_kind=EdgeKind.SELECTED_OUTCOME,
            label=outcome_value,
        )
