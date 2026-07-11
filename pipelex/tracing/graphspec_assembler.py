"""Reconstructs a GraphSpec from a flat list of trace events.

This is the core algorithm for distributed tracing — equivalent to
GraphTracer.teardown() but working from serialized events instead of
in-memory state. Used after Temporal execution to assemble cross-worker
graphs from NDJSON event files.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pipelex import log
from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    ErrorSpec,
    GraphSpec,
    GraphSpecMode,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
    TimingSpec,
    make_graphspec_meta,
    output_digest_is_optional,
)
from pipelex.tracing.trace_events import (
    BatchAggregateEvent,
    BatchItemEvent,
    ControllerOutputEvent,
    EdgeEvent,
    ExecutionDataEvent,
    ParallelCombineEvent,
    PipeEndErrorEvent,
    PipeEndSkippedEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
    UsageReportEvent,
)


class _AssemblerNodeData:
    """Internal mutable data structure for building a node from events.

    Mirrors _MutableNodeData from graph_tracer.py.
    """

    def __init__(
        self,
        node_id: str,
        pipe_code: str,
        pipe_type: str,
        node_kind: NodeKind,
        started_at: datetime,
        parent_node_id: str | None,
        input_specs: list[IOSpec] | None = None,
        description: str | None = None,
        domain_code: str | None = None,
    ) -> None:
        self.node_id = node_id
        self.pipe_code = pipe_code
        self.pipe_type = pipe_type
        self.node_kind = node_kind
        self.started_at = started_at
        self.parent_node_id = parent_node_id
        self.description = description
        self.domain_code = domain_code
        self.ended_at: datetime | None = None
        self.status: NodeStatus = NodeStatus.RUNNING
        self.skip_reason: str | None = None
        self.metrics: dict[str, float] = {}
        self.error: ErrorSpec | None = None
        self.input_specs: list[IOSpec] = input_specs or []
        self.output_specs: list[IOSpec] = []
        self.execution_data: dict[str, Any] = {}

    def to_node_spec(self) -> NodeSpec:
        """Convert to immutable NodeSpec."""
        assert self.started_at is not None
        assert self.ended_at is not None
        timing = TimingSpec(
            started_at=self.started_at,
            ended_at=self.ended_at,
        )

        node_io = NodeIOSpec(
            inputs=self.input_specs,
            outputs=list(self.output_specs),
        )

        return NodeSpec(
            node_id=self.node_id,
            kind=self.node_kind,
            pipe_code=self.pipe_code,
            pipe_type=self.pipe_type,
            description=self.description,
            domain_code=self.domain_code,
            status=self.status,
            skip_reason=self.skip_reason,
            timing=timing,
            node_io=node_io,
            error=self.error,
            metrics=self.metrics,
            execution_data=self.execution_data,
        )


class GraphSpecAssembler:
    """Reconstructs a GraphSpec from trace events.

    Two-pass algorithm:
    - Pass 1: Build nodes, producer map, and collect metadata from all events.
    - Pass 2: Generate DATA, BATCH_ITEM, BATCH_AGGREGATE, PARALLEL_COMBINE edges
      using the complete producer map.
    """

    @staticmethod
    def assemble(
        events: Sequence[TraceEvent],
        *,
        graph_id: str,
        pipeline_ref: PipelineRef | None = None,
        mode: GraphSpecMode = GraphSpecMode.LIVE,
    ) -> GraphSpec:
        """Assemble a GraphSpec from a flat list of trace events.

        Args:
            events: Flat list of trace events, pre-sorted by (workflow_id, sequence).
            graph_id: The graph identifier for the assembled GraphSpec.
            pipeline_ref: Optional pipeline reference metadata.
            mode: Provenance mode to stamp onto the assembled GraphSpec.

        Returns:
            A complete GraphSpec with nodes and edges.
        """
        assembler = _AssemblerState(graph_id=graph_id, pipeline_ref=pipeline_ref or PipelineRef(), mode=mode)
        assembler.pass_one(events)
        assembler.pass_two()
        return assembler.build_graph_spec()


class _AssemblerState:
    """Mutable state for a single assembler invocation."""

    def __init__(self, graph_id: str, pipeline_ref: PipelineRef, mode: GraphSpecMode) -> None:
        self._graph_id = graph_id
        self._pipeline_ref = pipeline_ref
        self._mode = mode
        self._earliest_timestamp: datetime | None = None

        # Pass 1 accumulation
        self._nodes: dict[str, _AssemblerNodeData] = {}
        self._explicit_edges: list[EdgeSpec] = []
        self._stuff_producer_map: dict[str, str] = {}
        self._batch_item_map: dict[str, tuple[str | None, list[tuple[str, int]]]] = {}
        self._batch_aggregate_map: dict[str, tuple[str | None, list[tuple[str, int]]]] = {}
        self._parallel_combine_map: dict[str, tuple[str, list[tuple[str, str]]]] = {}

        # Registries (accumulated from events, deduplicated)
        self._pipe_registry: dict[str, dict[str, Any]] = {}
        self._concept_registry: dict[str, dict[str, Any]] = {}

        # Edge ID counter for assembler-generated edges
        self._edge_sequence: int = 0
        # Edges generated in Pass 2 (DATA, BATCH_ITEM, etc.)
        self._generated_edges: list[EdgeSpec] = []

    def pass_one(self, events: Sequence[TraceEvent]) -> None:
        """Pass 1: Build nodes, producer map, and collect metadata."""
        for event in events:
            self._track_earliest_timestamp(event)

            if isinstance(event, PipeStartEvent):
                self._handle_pipe_start(event)
            elif isinstance(event, PipeEndSuccessEvent):
                self._handle_pipe_end_success(event)
            elif isinstance(event, PipeEndErrorEvent):
                self._handle_pipe_end_error(event)
            elif isinstance(event, PipeEndSkippedEvent):
                self._handle_pipe_end_skipped(event)
            elif isinstance(event, EdgeEvent):
                self._handle_edge_event(event)
            elif isinstance(event, ControllerOutputEvent):
                self._handle_controller_output(event)
            elif isinstance(event, BatchItemEvent):
                self._handle_batch_item(event)
            elif isinstance(event, BatchAggregateEvent):
                self._handle_batch_aggregate(event)
            elif isinstance(event, ParallelCombineEvent):
                self._handle_parallel_combine(event)
            elif isinstance(event, ExecutionDataEvent):
                self._handle_execution_data(event)
            elif isinstance(event, UsageReportEvent):
                pass  # Handled by UsageAggregator
            else:
                log.warning(f"Unknown event type: {type(event).__name__}")

        # Mark any still-running nodes as CANCELED
        self._mark_canceled_nodes()

    def pass_two(self) -> None:
        """Pass 2: Generate edges using the complete producer map."""
        self._generate_data_edges()
        self._generate_batch_item_edges()
        self._generate_batch_aggregate_edges()
        self._generate_parallel_combine_edges()

    def build_graph_spec(self) -> GraphSpec:
        """Build the final GraphSpec from accumulated state."""
        nodes = [node_data.to_node_spec() for node_data in self._nodes.values()]
        all_edges = self._explicit_edges + self._get_generated_edges()

        return GraphSpec(
            graph_id=self._graph_id,
            created_at=self._earliest_timestamp or datetime.now(UTC),
            pipeline_ref=self._pipeline_ref,
            nodes=nodes,
            edges=all_edges,
            meta=make_graphspec_meta(mode=self._mode),
            pipe_registry=dict(self._pipe_registry),
            concept_registry=dict(self._concept_registry),
        )

    # ------------------------------------------------------------------
    # Pass 1 handlers
    # ------------------------------------------------------------------

    def _track_earliest_timestamp(self, event: TraceEvent) -> None:
        if self._earliest_timestamp is None or event.timestamp < self._earliest_timestamp:
            self._earliest_timestamp = event.timestamp

    def _handle_pipe_start(self, event: PipeStartEvent) -> None:
        node_data = _AssemblerNodeData(
            node_id=event.node_id,
            pipe_code=event.pipe_code,
            pipe_type=event.pipe_type,
            node_kind=event.node_kind,
            started_at=event.timestamp,
            parent_node_id=event.parent_node_id,
            input_specs=list(event.input_specs),
            description=event.description,
            domain_code=event.domain_code,
        )
        self._nodes[event.node_id] = node_data

        # Accumulate pipe and concept registry data (deduplicated)
        if event.pipe_data:
            pipe_ref = f"{event.pipe_data.get('domain_code', '')}.{event.pipe_data.get('code', '')}"
            if pipe_ref not in self._pipe_registry:
                self._pipe_registry[pipe_ref] = event.pipe_data
        for concept_item in event.concept_data:
            concept_ref = f"{concept_item.get('domain_code', '')}.{concept_item.get('code', '')}"
            if concept_ref not in self._concept_registry:
                self._concept_registry[concept_ref] = concept_item

    def _handle_pipe_end_success(self, event: PipeEndSuccessEvent) -> None:
        node_data = self._nodes.get(event.node_id)
        if node_data is None:
            log.warning(f"PipeEndSuccessEvent for unknown node: {event.node_id}")
            return

        node_data.ended_at = event.ended_at
        node_data.status = NodeStatus.SUCCEEDED
        if event.metrics:
            node_data.metrics = event.metrics

        # Accumulate output concept data (deduplicated)
        if event.output_concept_data:
            concept_ref = f"{event.output_concept_data.get('domain_code', '')}.{event.output_concept_data.get('code', '')}"
            if concept_ref not in self._concept_registry:
                self._concept_registry[concept_ref] = event.output_concept_data

        # Pass-through detection (mirrors graph_tracer.py:476-488)
        if event.output_spec is not None:
            input_digests = {spec.digest for spec in node_data.input_specs if spec.digest is not None}
            if event.output_spec.digest in input_digests:
                # Pass-through: don't register as output or producer
                pass
            else:
                node_data.output_specs.append(event.output_spec)
                if event.output_spec.digest:
                    self._stuff_producer_map[event.output_spec.digest] = event.node_id

    def _handle_pipe_end_error(self, event: PipeEndErrorEvent) -> None:
        node_data = self._nodes.get(event.node_id)
        if node_data is None:
            log.warning(f"PipeEndErrorEvent for unknown node: {event.node_id}")
            return

        node_data.ended_at = event.ended_at
        node_data.status = NodeStatus.FAILED
        node_data.error = event.error

    def _handle_pipe_end_skipped(self, event: PipeEndSkippedEvent) -> None:
        node_data = self._nodes.get(event.node_id)
        if node_data is None:
            log.warning(f"PipeEndSkippedEvent for unknown node: {event.node_id}")
            return

        node_data.ended_at = event.ended_at
        node_data.status = NodeStatus.SKIPPED
        node_data.skip_reason = event.skip_reason

        # A lifted pipe with a PLURAL output still wrote a real empty-list Stuff (D4) — register
        # it so downstream DATA edges resolve (mirrors GraphTracer.on_pipe_end_skipped).
        if event.output_concept_data:
            concept_ref = f"{event.output_concept_data.get('domain_code', '')}.{event.output_concept_data.get('code', '')}"
            if concept_ref not in self._concept_registry:
                self._concept_registry[concept_ref] = event.output_concept_data
        if event.output_spec is not None:
            input_digests = {spec.digest for spec in node_data.input_specs if spec.digest is not None}
            if event.output_spec.digest not in input_digests:
                node_data.output_specs.append(event.output_spec)
                if event.output_spec.digest:
                    self._stuff_producer_map[event.output_spec.digest] = event.node_id

    def _handle_edge_event(self, event: EdgeEvent) -> None:
        # DATA, BATCH_ITEM, BATCH_AGGREGATE, PARALLEL_COMBINE are regenerated
        # in pass 2 with full cross-worker visibility — skip to avoid duplicates.
        match event.edge_kind:
            case EdgeKind.CONTAINS | EdgeKind.SELECTED_OUTCOME | EdgeKind.CONTROL:
                edge = EdgeSpec(
                    edge_id=event.edge_id,
                    source=event.source_node_id,
                    target=event.target_node_id,
                    kind=event.edge_kind,
                    optional=event.optional,
                    label=event.label,
                    source_stuff_digest=event.source_stuff_digest,
                    target_stuff_digest=event.target_stuff_digest,
                )
                self._explicit_edges.append(edge)
            case EdgeKind.DATA | EdgeKind.BATCH_ITEM | EdgeKind.BATCH_AGGREGATE | EdgeKind.PARALLEL_COMBINE:
                pass  # Regenerated in pass 2

    def _handle_controller_output(self, event: ControllerOutputEvent) -> None:
        node_data = self._nodes.get(event.node_id)
        if node_data is None:
            log.warning(f"ControllerOutputEvent for unknown node: {event.node_id}")
            return

        node_data.output_specs.append(event.output_spec)
        if event.output_spec.digest:
            self._stuff_producer_map[event.output_spec.digest] = event.node_id

    def _handle_execution_data(self, event: ExecutionDataEvent) -> None:
        node_data = self._nodes.get(event.node_id)
        if node_data is None:
            log.warning(f"ExecutionDataEvent for unknown node: {event.node_id}")
            return
        node_data.execution_data.update(event.execution_data)

    def _handle_batch_item(self, event: BatchItemEvent) -> None:
        if event.list_stuff_code not in self._batch_item_map:
            self._batch_item_map[event.list_stuff_code] = (event.batch_controller_node_id, [])
        _existing_controller_id, item_list = self._batch_item_map[event.list_stuff_code]
        item_list.append((event.item_stuff_code, event.item_index))

    def _handle_batch_aggregate(self, event: BatchAggregateEvent) -> None:
        if event.output_list_stuff_code not in self._batch_aggregate_map:
            self._batch_aggregate_map[event.output_list_stuff_code] = (event.batch_controller_node_id, [])
        _existing_controller_id, item_list = self._batch_aggregate_map[event.output_list_stuff_code]
        item_list.append((event.item_stuff_code, event.item_index))

    def _handle_parallel_combine(self, event: ParallelCombineEvent) -> None:
        # branch_producer_node_ids already snapshotted at emit time
        self._parallel_combine_map[event.combined_stuff_code] = (
            event.parallel_controller_node_id,
            list(event.branch_producer_node_ids),
        )

    def _mark_canceled_nodes(self) -> None:
        """Mark any still-RUNNING nodes as CANCELED (mirrors graph_tracer.py:160-164)."""
        for node_data in self._nodes.values():
            if node_data.status == NodeStatus.RUNNING:
                node_data.status = NodeStatus.CANCELED
                node_data.ended_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Pass 2 edge generation
    # ------------------------------------------------------------------

    def _make_edge_id(self) -> str:
        edge_id = f"{self._graph_id}:asm_edge_{self._edge_sequence}"
        self._edge_sequence += 1
        return edge_id

    def _get_generated_edges(self) -> list[EdgeSpec]:
        """Return all edges generated in Pass 2 (stored via _add_generated_edge)."""
        return self._generated_edges

    def _add_generated_edge(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
        source_stuff_digest: str | None = None,
        target_stuff_digest: str | None = None,
        optional: bool = False,
    ) -> None:
        edge = EdgeSpec(
            edge_id=self._make_edge_id(),
            source=source_node_id,
            target=target_node_id,
            kind=edge_kind,
            optional=optional,
            label=label,
            source_stuff_digest=source_stuff_digest,
            target_stuff_digest=target_stuff_digest,
        )
        self._generated_edges.append(edge)

    def _is_optional_output_digest(self, *, producer_node_id: str, digest: str) -> bool:
        """Whether the producer registered this digest as a declared-optional (`?`) output.

        Node lookup here; the marker semantics live in the shared `output_digest_is_optional`.
        """
        producer_data = self._nodes.get(producer_node_id)
        if producer_data is None:
            return False
        return output_digest_is_optional(producer_data.output_specs, digest=digest)

    def _generate_data_edges(self) -> None:
        """Generate DATA edges by correlating input digests with producer nodes.

        Mirrors GraphTracer._generate_data_edges() (graph_tracer.py:199-222).
        """
        for consumer_node_id, node_data in self._nodes.items():
            for input_spec in node_data.input_specs:
                if input_spec.digest is None:
                    continue
                producer_node_id = self._stuff_producer_map.get(input_spec.digest)
                if producer_node_id is None:
                    continue
                if producer_node_id == consumer_node_id:
                    continue
                self._add_generated_edge(
                    source_node_id=producer_node_id,
                    target_node_id=consumer_node_id,
                    edge_kind=EdgeKind.DATA,
                    label=input_spec.name,
                    optional=self._is_optional_output_digest(producer_node_id=producer_node_id, digest=input_spec.digest),
                )

    def _generate_batch_item_edges(self) -> None:
        """Generate BATCH_ITEM edges for batch fan-out.

        Mirrors GraphTracer._generate_batch_item_edges() (graph_tracer.py:224-267).
        """
        for list_stuff_code, (batch_controller_node_id, item_entries) in self._batch_item_map.items():
            list_producer_node_id = self._stuff_producer_map.get(list_stuff_code)
            source_node_id = batch_controller_node_id or list_producer_node_id

            if not source_node_id:
                # Legacy fallback: scan all nodes for a consumer of the list
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
                for consumer_node_id, node_data in self._nodes.items():
                    for input_spec in node_data.input_specs:
                        if input_spec.digest == item_stuff_code:
                            if source_node_id != consumer_node_id:
                                self._add_generated_edge(
                                    source_node_id=source_node_id,
                                    target_node_id=consumer_node_id,
                                    edge_kind=EdgeKind.BATCH_ITEM,
                                    label=f"[{item_index}]",
                                    source_stuff_digest=list_stuff_code,
                                    target_stuff_digest=item_stuff_code,
                                )
                            break

    def _generate_batch_aggregate_edges(self) -> None:
        """Generate BATCH_AGGREGATE edges from item producers to output list.

        Mirrors GraphTracer._generate_batch_aggregate_edges() (graph_tracer.py:269-301).
        """
        for output_list_stuff_code, (batch_controller_node_id, item_entries) in self._batch_aggregate_map.items():
            target_node_id = batch_controller_node_id or self._stuff_producer_map.get(output_list_stuff_code)
            if not target_node_id:
                continue

            for item_stuff_code, item_index in item_entries:
                item_producer_id = self._stuff_producer_map.get(item_stuff_code)
                if item_producer_id and item_producer_id != target_node_id:
                    self._add_generated_edge(
                        source_node_id=item_producer_id,
                        target_node_id=target_node_id,
                        edge_kind=EdgeKind.BATCH_AGGREGATE,
                        label=f"[{item_index}]",
                        source_stuff_digest=item_stuff_code,
                        target_stuff_digest=output_list_stuff_code,
                    )

    def _generate_parallel_combine_edges(self) -> None:
        """Generate PARALLEL_COMBINE edges from branch producers to controller.

        Mirrors GraphTracer._generate_parallel_combine_edges() (graph_tracer.py:303-321).
        """
        for combined_stuff_code, (parallel_controller_node_id, branch_entries) in self._parallel_combine_map.items():
            for branch_stuff_code, branch_producer_id in branch_entries:
                if branch_producer_id != parallel_controller_node_id:
                    self._add_generated_edge(
                        source_node_id=branch_producer_id,
                        target_node_id=parallel_controller_node_id,
                        edge_kind=EdgeKind.PARALLEL_COMBINE,
                        source_stuff_digest=branch_stuff_code,
                        target_stuff_digest=combined_stuff_code,
                    )
