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
        self.output_spec: IOSpec | None = None

    def to_node_spec(self) -> NodeSpec:
        """Convert to immutable NodeSpec."""
        assert self.started_at is not None
        assert self.ended_at is not None
        timing = TimingSpec(
            started_at=self.started_at,
            ended_at=self.ended_at,
        )

        # Build NodeIOSpec from captured input/output specs
        outputs: list[IOSpec] = []
        if self.output_spec is not None:
            outputs = [self.output_spec]

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

    @property
    def is_active(self) -> bool:
        """Whether tracing is currently active."""
        return self._is_active

    @override
    def setup(
        self,
        graph_id: str,
        data_inclusion: DataInclusionConfig,
        pipeline_ref_domain: str | None = None,
        pipeline_ref_main_pipe: str | None = None,
    ) -> GraphContext:
        """Initialize tracing for a new pipeline run."""
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

        # Generate node ID
        node_id = f"{self._graph_id}:node_{self._node_sequence}"
        self._node_sequence += 1

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
            node_data.output_spec = output_spec
            # Register this node as the producer of this stuff_code (digest)
            if output_spec.digest:
                self._stuff_producer_map[output_spec.digest] = node_id

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
        node_data.error = ErrorSpec(
            error_type=error_type,
            message=error_message,
            stack=error_stack,
        )

    @override
    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_kind: EdgeKind,
        label: str | None = None,
    ) -> None:
        """Add an edge between two nodes."""
        if not self._is_active:
            return

        edge_id = f"{self._graph_id}:edge_{self._edge_sequence}"
        self._edge_sequence += 1

        edge = EdgeSpec(
            edge_id=edge_id,
            source=source_node_id,
            target=target_node_id,
            kind=edge_kind,
            label=label,
        )
        self._edges.append(edge)

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
