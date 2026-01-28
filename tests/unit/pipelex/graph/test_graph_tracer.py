"""Unit tests for GraphTracer."""

from datetime import datetime, timedelta, timezone

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import EdgeKind, IOSpec, NodeKind, NodeStatus
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config


class TestGraphTracer:
    """Tests for GraphTracer implementation."""

    def test_setup_returns_initial_context(self) -> None:
        """Test that setup returns a properly initialized GraphContext."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="test-graph-001", data_inclusion=make_defaulted_data_inclusion_config())

        assert context.graph_id == "test-graph-001"
        assert context.parent_node_id is None
        assert context.node_sequence == 0

    def test_setup_with_pipeline_ref(self) -> None:
        """Test that setup accepts pipeline reference parameters."""
        tracer = GraphTracer()
        context = tracer.setup(
            graph_id="test-graph-002",
            data_inclusion=make_defaulted_data_inclusion_config(),
            pipeline_ref_domain="test.domain",
            pipeline_ref_main_pipe="main_pipe",
        )

        assert context.graph_id == "test-graph-002"
        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert graph_spec.pipeline_ref.domain == "test.domain"
        assert graph_spec.pipeline_ref.main_pipe == "main_pipe"

    def test_teardown_without_setup_returns_none(self) -> None:
        """Test that teardown returns None if not active."""
        tracer = GraphTracer()
        result = tracer.teardown()

        assert result is None

    def test_full_lifecycle_single_node(self) -> None:
        """Test tracking a single pipe execution."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="lifecycle-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        node_id, child_context = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        assert node_id == "lifecycle-test:node_0"
        assert child_context.parent_node_id == node_id

        ended_at = started_at + timedelta(milliseconds=100)
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=ended_at,
            metrics={"tokens": 150.0},
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.nodes) == 1
        assert len(graph_spec.edges) == 0

        node = graph_spec.nodes[0]
        assert node.node_id == "lifecycle-test:node_0"
        assert node.pipe_code == "test_pipe"
        assert node.pipe_type == "PipeLLM"
        assert node.kind == NodeKind.OPERATOR
        assert node.status == NodeStatus.SUCCEEDED
        assert node.timing is not None
        assert node.timing.started_at == started_at
        assert node.timing.ended_at == ended_at
        assert node.timing.duration == 0.1
        assert node.metrics == {"tokens": 150.0}

    def test_nested_pipe_execution(self) -> None:
        """Test tracking nested pipe execution with containment edges."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="nested-test", data_inclusion=make_defaulted_data_inclusion_config())

        # Start parent (sequence controller)
        started_at = datetime.now(timezone.utc)
        parent_id, parent_child_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_sequence",
            pipe_type="PipeSequence",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        # Start child 1 (operator)
        child1_id, _child1_ctx = tracer.on_pipe_start(
            graph_context=parent_child_ctx,
            pipe_code="llm_step_1",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )

        tracer.on_pipe_end_success(
            node_id=child1_id,
            ended_at=started_at + timedelta(milliseconds=50),
        )

        # Start child 2 (operator)
        child2_id, _child2_ctx = tracer.on_pipe_start(
            graph_context=parent_child_ctx,
            pipe_code="llm_step_2",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=60),
        )

        tracer.on_pipe_end_success(
            node_id=child2_id,
            ended_at=started_at + timedelta(milliseconds=100),
        )

        # End parent
        tracer.on_pipe_end_success(
            node_id=parent_id,
            ended_at=started_at + timedelta(milliseconds=110),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.nodes) == 3
        assert len(graph_spec.edges) == 2  # parent -> child1, parent -> child2

        # Check containment edges
        edges = graph_spec.edges
        assert all(edge.kind == EdgeKind.CONTAINS for edge in edges)
        assert {edge.source for edge in edges} == {parent_id}
        assert {edge.target for edge in edges} == {child1_id, child2_id}

    def test_error_tracking(self) -> None:
        """Test tracking failed pipe execution."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="error-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="failing_pipe",
            pipe_type="PipeFunc",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        tracer.on_pipe_end_error(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=50),
            error_type="ValueError",
            error_message="Something went wrong",
            error_stack="Traceback...",
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        node = graph_spec.nodes[0]
        assert node.status == NodeStatus.FAILED
        assert node.error is not None
        assert node.error.error_type == "ValueError"
        assert node.error.message == "Something went wrong"
        assert node.error.stack == "Traceback..."

    def test_running_nodes_marked_canceled_on_teardown(self) -> None:
        """Test that running nodes are marked as canceled on teardown."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="cancel-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        _node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="stuck_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        # Don't call on_pipe_end_* - node stays running
        graph_spec = tracer.teardown()

        assert graph_spec is not None
        node = graph_spec.nodes[0]
        assert node.status == NodeStatus.CANCELED
        assert node.timing is not None
        assert node.timing.ended_at is not None

    def test_custom_edges(self) -> None:
        """Test adding custom edges between nodes."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="edge-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        node1_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="pipe_1",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(node_id=node1_id, ended_at=started_at + timedelta(milliseconds=10))

        node2_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="pipe_2",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=20),
        )
        tracer.on_pipe_end_success(node_id=node2_id, ended_at=started_at + timedelta(milliseconds=30))

        # Add data flow edge
        tracer.add_edge(
            source_node_id=node1_id,
            target_node_id=node2_id,
            edge_kind=EdgeKind.DATA,
            label="output_text",
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.edges) == 1
        edge = graph_spec.edges[0]
        assert edge.source == node1_id
        assert edge.target == node2_id
        assert edge.kind == EdgeKind.DATA
        assert edge.label == "output_text"

    def test_selected_outcome_edge(self) -> None:
        """Test adding selected outcome edge for conditions."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="condition-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        condition_id, cond_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_condition",
            pipe_type="PipeCondition",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        outcome_id, _ = tracer.on_pipe_start(
            graph_context=cond_ctx,
            pipe_code="outcome_true",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )
        tracer.on_pipe_end_success(node_id=outcome_id, ended_at=started_at + timedelta(milliseconds=20))

        # Mark the selected outcome
        tracer.add_selected_outcome_edge(
            condition_node_id=condition_id,
            outcome_node_id=outcome_id,
            outcome_value="true",
        )

        tracer.on_pipe_end_success(node_id=condition_id, ended_at=started_at + timedelta(milliseconds=25))

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        selected_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.SELECTED_OUTCOME]
        assert len(selected_edges) == 1
        assert selected_edges[0].label == "true"

    def test_input_specs_captured(self) -> None:
        """Test that input IOSpecs are captured and stored in node_io."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="io-test", data_inclusion=make_defaulted_data_inclusion_config())

        input_specs = [
            IOSpec(name="document", concept="Text", digest="abc12"),
            IOSpec(name="query", concept="Text", digest="def34"),
        ]

        started_at = datetime.now(timezone.utc)
        node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
            input_specs=input_specs,
        )
        tracer.on_pipe_end_success(node_id=node_id, ended_at=started_at + timedelta(milliseconds=50))

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        node = graph_spec.nodes[0]
        assert len(node.node_io.inputs) == 2
        assert node.node_io.inputs[0].name == "document"
        assert node.node_io.inputs[0].digest == "abc12"
        assert node.node_io.inputs[1].name == "query"
        assert node.node_io.inputs[1].digest == "def34"

    def test_output_spec_captured(self) -> None:
        """Test that output IOSpec is captured and stored in node_io."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="io-test", data_inclusion=make_defaulted_data_inclusion_config())

        output_spec = IOSpec(
            name="summary",
            concept="Text",
            content_type="TextContent",
            digest="xyz99",
        )

        started_at = datetime.now(timezone.utc)
        node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="summarize",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=output_spec,
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        node = graph_spec.nodes[0]
        assert len(node.node_io.outputs) == 1
        assert node.node_io.outputs[0].name == "summary"
        assert node.node_io.outputs[0].digest == "xyz99"
        assert node.node_io.outputs[0].content_type == "TextContent"

    def test_data_edge_generation_from_stuff_codes(self) -> None:
        """Test that DATA edges are created when stuff_codes match between output and input."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="data-flow-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # Pipe 1: produces stuff with digest "stuff_001"
        node1_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="producer_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(
            node_id=node1_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="output_text", concept="Text", digest="stuff_001"),
        )

        # Pipe 2: consumes stuff with digest "stuff_001"
        node2_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="consumer_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=60),
            input_specs=[IOSpec(name="input_text", concept="Text", digest="stuff_001")],
        )
        tracer.on_pipe_end_success(
            node_id=node2_id,
            ended_at=started_at + timedelta(milliseconds=100),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        data_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.DATA]
        assert len(data_edges) == 1
        assert data_edges[0].source == node1_id
        assert data_edges[0].target == node2_id
        assert data_edges[0].label == "input_text"

    def test_data_edge_not_created_for_unknown_producer(self) -> None:
        """Test that no DATA edge is created if the producer is unknown (initial pipeline input)."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="no-producer-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # Pipe consumes stuff that wasn't produced by any tracked pipe
        node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="consumer_only",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
            input_specs=[IOSpec(name="initial_input", concept="Text", digest="unknown_stuff")],
        )
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=50),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        data_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.DATA]
        assert len(data_edges) == 0

    def test_no_self_loop_data_edges(self) -> None:
        """Test that DATA edges are not created as self-loops."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="no-self-loop-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # Pipe produces and consumes the same stuff (shouldn't happen, but guard against it)
        node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="self_ref_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
            input_specs=[IOSpec(name="input", concept="Text", digest="same_stuff")],
        )
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="output", concept="Text", digest="same_stuff"),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        data_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.DATA]
        # Should be 0 - no self-loops
        assert len(data_edges) == 0

    def test_multiple_consumers_same_stuff(self) -> None:
        """Test DATA edges when multiple pipes consume the same stuff."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="multi-consumer-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # Producer pipe
        producer_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="producer",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(
            node_id=producer_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="shared_output", concept="Text", digest="shared_stuff"),
        )

        # Consumer 1
        consumer1_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="consumer_1",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=60),
            input_specs=[IOSpec(name="input_a", concept="Text", digest="shared_stuff")],
        )
        tracer.on_pipe_end_success(node_id=consumer1_id, ended_at=started_at + timedelta(milliseconds=80))

        # Consumer 2
        consumer2_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="consumer_2",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=90),
            input_specs=[IOSpec(name="input_b", concept="Text", digest="shared_stuff")],
        )
        tracer.on_pipe_end_success(node_id=consumer2_id, ended_at=started_at + timedelta(milliseconds=110))

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        data_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.DATA]
        assert len(data_edges) == 2

        # Both edges should have producer as source
        assert all(edge.source == producer_id for edge in data_edges)
        targets = {edge.target for edge in data_edges}
        assert targets == {consumer1_id, consumer2_id}

    def test_batch_item_edge_generation(self) -> None:
        """Test BATCH_ITEM edges are created for list item extraction.

        When a batch controller extracts items from a list, edges should be
        created from the list consumer to the item consumers.
        """
        tracer = GraphTracer()
        context = tracer.setup(graph_id="batch-item-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # PipeBatch that consumes the list
        batch_id, batch_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_batch",
            pipe_type="PipeBatch",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
            input_specs=[IOSpec(name="articles", concept="List", digest="list_stuff_001")],
        )

        # Branch 0: processes item 0
        branch0_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="branch_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
            input_specs=[IOSpec(name="article", concept="Text", digest="item_stuff_000")],
        )
        tracer.on_pipe_end_success(
            node_id=branch0_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="summary", concept="Text", digest="output_000"),
        )

        # Branch 1: processes item 1
        branch1_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="branch_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
            input_specs=[IOSpec(name="article", concept="Text", digest="item_stuff_001")],
        )
        tracer.on_pipe_end_success(
            node_id=branch1_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="summary", concept="Text", digest="output_001"),
        )

        # Register batch item extractions
        tracer.register_batch_item_extraction(
            list_stuff_code="list_stuff_001",
            item_stuff_code="item_stuff_000",
            item_index=0,
        )
        tracer.register_batch_item_extraction(
            list_stuff_code="list_stuff_001",
            item_stuff_code="item_stuff_001",
            item_index=1,
        )

        tracer.on_pipe_end_success(
            node_id=batch_id,
            ended_at=started_at + timedelta(milliseconds=100),
            output_spec=IOSpec(name="summaries", concept="List", digest="output_list"),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        batch_item_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_ITEM]
        assert len(batch_item_edges) == 2

        # Both edges should have batch_id as source (the list consumer)
        assert all(edge.source == batch_id for edge in batch_item_edges)
        targets = {edge.target for edge in batch_item_edges}
        assert targets == {branch0_id, branch1_id}

        # Check labels contain indices
        labels = {edge.label for edge in batch_item_edges}
        assert labels == {"[0]", "[1]"}

    def test_batch_aggregate_edge_generation(self) -> None:
        """Test BATCH_AGGREGATE edges are created for output list aggregation.

        When a batch controller aggregates outputs into a list, edges should be
        created from the item producers to the list producer.
        """
        tracer = GraphTracer()
        context = tracer.setup(graph_id="batch-aggregate-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # PipeBatch that produces the output list
        batch_id, batch_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_batch",
            pipe_type="PipeBatch",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
            input_specs=[IOSpec(name="articles", concept="List", digest="list_input")],
        )

        # Branch 0: produces item 0
        branch0_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="branch_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )
        tracer.on_pipe_end_success(
            node_id=branch0_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="summary", concept="Text", digest="branch_output_000"),
        )

        # Branch 1: produces item 1
        branch1_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="branch_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )
        tracer.on_pipe_end_success(
            node_id=branch1_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="summary", concept="Text", digest="branch_output_001"),
        )

        # Register batch aggregations
        tracer.register_batch_aggregation(
            output_list_stuff_code="output_list_stuff",
            item_stuff_code="branch_output_000",
            item_index=0,
        )
        tracer.register_batch_aggregation(
            output_list_stuff_code="output_list_stuff",
            item_stuff_code="branch_output_001",
            item_index=1,
        )

        tracer.on_pipe_end_success(
            node_id=batch_id,
            ended_at=started_at + timedelta(milliseconds=100),
            output_spec=IOSpec(name="summaries", concept="List", digest="output_list_stuff"),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        batch_aggregate_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_AGGREGATE]
        assert len(batch_aggregate_edges) == 2

        # Both edges should have batch_id as target (the list producer)
        assert all(edge.target == batch_id for edge in batch_aggregate_edges)
        sources = {edge.source for edge in batch_aggregate_edges}
        assert sources == {branch0_id, branch1_id}

        # Check labels contain indices
        labels = {edge.label for edge in batch_aggregate_edges}
        assert labels == {"[0]", "[1]"}

    def test_batch_edges_combined(self) -> None:
        """Test both BATCH_ITEM and BATCH_AGGREGATE edges in a complete batch scenario."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="batch-combined-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # PipeBatch
        batch_id, batch_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_batch",
            pipe_type="PipeBatch",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
            input_specs=[IOSpec(name="items", concept="List", digest="input_list")],
        )

        # Branch 0
        branch0_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="process_item",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=5),
            input_specs=[IOSpec(name="item", concept="Text", digest="item_0")],
        )
        tracer.on_pipe_end_success(
            node_id=branch0_id,
            ended_at=started_at + timedelta(milliseconds=30),
            output_spec=IOSpec(name="result", concept="Text", digest="result_0"),
        )

        # Register extractions and aggregations
        tracer.register_batch_item_extraction(
            list_stuff_code="input_list",
            item_stuff_code="item_0",
            item_index=0,
        )
        tracer.register_batch_aggregation(
            output_list_stuff_code="output_list",
            item_stuff_code="result_0",
            item_index=0,
        )

        tracer.on_pipe_end_success(
            node_id=batch_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="results", concept="List", digest="output_list"),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None

        batch_item_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_ITEM]
        batch_aggregate_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_AGGREGATE]

        assert len(batch_item_edges) == 1
        assert len(batch_aggregate_edges) == 1

        # BATCH_ITEM: batch -> branch
        assert batch_item_edges[0].source == batch_id
        assert batch_item_edges[0].target == branch0_id
        assert batch_item_edges[0].label == "[0]"

        # BATCH_AGGREGATE: branch -> batch
        assert batch_aggregate_edges[0].source == branch0_id
        assert batch_aggregate_edges[0].target == batch_id
        assert batch_aggregate_edges[0].label == "[0]"

    def test_batch_registration_inactive_tracer(self) -> None:
        """Test that batch registrations are ignored when tracer is not active."""
        tracer = GraphTracer()

        # Don't call setup - tracer is inactive
        tracer.register_batch_item_extraction(
            list_stuff_code="list",
            item_stuff_code="item",
            item_index=0,
        )
        tracer.register_batch_aggregation(
            output_list_stuff_code="output",
            item_stuff_code="item",
            item_index=0,
        )

        # Teardown should return None since tracer was never active
        result = tracer.teardown()
        assert result is None

    def test_batch_item_edges_contain_stuff_digests(self) -> None:
        """Test that BATCH_ITEM edges include source and target stuff digests.

        The source_stuff_digest should be the list stuff code,
        and target_stuff_digest should be the item stuff code.
        """
        tracer = GraphTracer()
        context = tracer.setup(graph_id="batch-digest-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # PipeBatch that consumes the list
        batch_id, batch_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_batch",
            pipe_type="PipeBatch",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
            input_specs=[IOSpec(name="articles", concept="List", digest="list_digest_abc")],
        )

        # Branch: processes item
        branch_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="branch_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
            input_specs=[IOSpec(name="article", concept="Text", digest="item_digest_xyz")],
        )
        tracer.on_pipe_end_success(
            node_id=branch_id,
            ended_at=started_at + timedelta(milliseconds=50),
        )

        # Register batch item extraction
        tracer.register_batch_item_extraction(
            list_stuff_code="list_digest_abc",
            item_stuff_code="item_digest_xyz",
            item_index=0,
        )

        tracer.on_pipe_end_success(
            node_id=batch_id,
            ended_at=started_at + timedelta(milliseconds=100),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        batch_item_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_ITEM]
        assert len(batch_item_edges) == 1

        edge = batch_item_edges[0]
        assert edge.source_stuff_digest == "list_digest_abc"
        assert edge.target_stuff_digest == "item_digest_xyz"

    def test_batch_aggregate_edges_contain_stuff_digests(self) -> None:
        """Test that BATCH_AGGREGATE edges include source and target stuff digests.

        The source_stuff_digest should be the item stuff code,
        and target_stuff_digest should be the output list stuff code.
        """
        tracer = GraphTracer()
        context = tracer.setup(graph_id="batch-agg-digest-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)

        # PipeBatch
        batch_id, batch_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_batch",
            pipe_type="PipeBatch",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
            input_specs=[IOSpec(name="items", concept="List", digest="input_list")],
        )

        # Branch: produces item
        branch_id, _ = tracer.on_pipe_start(
            graph_context=batch_ctx,
            pipe_code="branch_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )
        tracer.on_pipe_end_success(
            node_id=branch_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="result", concept="Text", digest="item_result_digest"),
        )

        # Register batch aggregation
        tracer.register_batch_aggregation(
            output_list_stuff_code="output_list_digest",
            item_stuff_code="item_result_digest",
            item_index=0,
        )

        tracer.on_pipe_end_success(
            node_id=batch_id,
            ended_at=started_at + timedelta(milliseconds=100),
            output_spec=IOSpec(name="results", concept="List", digest="output_list_digest"),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        batch_aggregate_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_AGGREGATE]
        assert len(batch_aggregate_edges) == 1

        edge = batch_aggregate_edges[0]
        assert edge.source_stuff_digest == "item_result_digest"
        assert edge.target_stuff_digest == "output_list_digest"
