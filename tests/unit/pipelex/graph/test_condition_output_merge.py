"""Unit tests for the rewrite that gives every outcome of a dry-run condition the condition's output digest."""

from datetime import UTC, datetime
from typing import ClassVar

import pytest

from pipelex.graph.condition_output_merge import ConditionOutputMerge, ConditionOutputTyping, apply_condition_output_merges
from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, IOSpec, NodeIOSpec, NodeKind, NodeSpec, NodeStatus


def _node(*, node_id: str, kind: NodeKind = NodeKind.OPERATOR, inputs: list[IOSpec] | None = None, outputs: list[IOSpec] | None = None) -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        kind=kind,
        pipe_code=node_id,
        status=NodeStatus.SUCCEEDED,
        node_io=NodeIOSpec(inputs=inputs or [], outputs=outputs or []),
    )


def _contains(*, source: str, target: str) -> EdgeSpec:
    return EdgeSpec(edge_id=f"contains_{source}_{target}", source=source, target=target, kind=EdgeKind.CONTAINS)


def _outputs_by_node(graph: GraphSpec) -> dict[str, list[IOSpec]]:
    return {node.node_id: node.node_io.outputs for node in graph.nodes}


def _inputs_by_node(graph: GraphSpec) -> dict[str, list[IOSpec]]:
    return {node.node_id: node.node_io.inputs for node in graph.nodes}


class TestApplyConditionOutputMerges:
    CREATED_AT: ClassVar[datetime] = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)

    def _graph(self, *, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> GraphSpec:
        return GraphSpec(graph_id="merge_test", created_at=self.CREATED_AT, nodes=nodes, edges=edges)

    def _report_shape(self) -> GraphSpec:
        """`route` runs `write_questions` then `write_rejection`, whose stuff `assemble` reads."""
        return self._graph(
            nodes=[
                _node(
                    node_id="route",
                    kind=NodeKind.CONTROLLER,
                    inputs=[IOSpec(name="verdict", concept="Text", digest="d_verdict")],
                    outputs=[IOSpec(name="follow_up", concept="Rejection", digest="d_rejection")],
                ),
                _node(node_id="write_questions", outputs=[IOSpec(name="follow_up", concept="Question", multiplicity=True, digest="d_questions")]),
                _node(node_id="write_rejection", outputs=[IOSpec(name="follow_up", concept="Rejection", digest="d_rejection")]),
                _node(
                    node_id="assemble",
                    inputs=[
                        IOSpec(name="verdict", concept="Text", digest="d_verdict"),
                        IOSpec(name="follow_up", concept="Anything", digest="d_rejection"),
                    ],
                    outputs=[IOSpec(name="result", concept="Text", digest="d_result")],
                ),
            ],
            edges=[
                _contains(source="route", target="write_questions"),
                _contains(source="route", target="write_rejection"),
                EdgeSpec(edge_id="data_route_assemble", source="route", target="assemble", kind=EdgeKind.DATA, label="follow_up"),
            ],
        )

    def test_no_merge_leaves_the_graph_alone(self) -> None:
        graph = self._report_shape()
        assert apply_condition_output_merges(graph=graph, merges=[]) == graph

    def test_every_outcome_takes_the_shared_digest(self) -> None:
        graph = self._report_shape()
        merge = ConditionOutputMerge(condition_node_id="route", shared_digest="d_rejection", merged_digests=["d_questions"])

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        outputs = _outputs_by_node(merged)
        assert [spec.digest for spec in outputs["write_questions"]] == ["d_rejection"]
        assert [spec.digest for spec in outputs["write_rejection"]] == ["d_rejection"]
        assert [spec.digest for spec in outputs["route"]] == ["d_rejection"]
        assert [spec.digest for spec in _inputs_by_node(merged)["assemble"]] == ["d_verdict", "d_rejection"]
        # Each outcome keeps what it writes: only the digest moves.
        assert outputs["write_questions"][0].concept == "Question"
        assert outputs["write_questions"][0].multiplicity is True
        # Without a typing, the condition's own item is untouched.
        assert outputs["route"][0].concept == "Rejection"

    def test_a_typing_retypes_the_condition_item_only(self) -> None:
        graph = self._report_shape()
        merge = ConditionOutputMerge(
            condition_node_id="route",
            shared_digest="d_rejection",
            merged_digests=["d_questions"],
            shared_typing=ConditionOutputTyping(concept="Anything", multiplicity=None),
        )

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        outputs = _outputs_by_node(merged)
        assert outputs["route"][0].concept == "Anything"
        assert outputs["route"][0].multiplicity is None
        assert outputs["write_questions"][0].concept == "Question"
        assert outputs["write_questions"][0].multiplicity is True
        assert outputs["write_rejection"][0].concept == "Rejection"
        assert _inputs_by_node(merged)["assemble"][1].concept == "Anything"
        assert _inputs_by_node(merged)["route"][0].concept == "Text"

    def test_a_typing_types_a_list(self) -> None:
        graph = self._report_shape()
        merge = ConditionOutputMerge(
            condition_node_id="route",
            shared_digest="d_rejection",
            merged_digests=["d_questions"],
            shared_typing=ConditionOutputTyping(concept="Question", multiplicity=True),
        )

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        route_output = _outputs_by_node(merged)["route"][0]
        assert route_output.concept_label == "Question[]"

    @pytest.mark.parametrize("inner_first", [True, False])
    def test_a_nested_condition_lands_on_the_outer_digest(self, *, inner_first: bool) -> None:
        """`outer` runs `inner` then `fallback`; `inner` runs `x` then `y`. Every one ends on `fallback`'s digest."""
        graph = self._graph(
            nodes=[
                _node(node_id="outer", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", digest="d_fallback")]),
                _node(node_id="inner", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", digest="d_y")]),
                _node(node_id="x", outputs=[IOSpec(name="slot", digest="d_x")]),
                _node(node_id="y", outputs=[IOSpec(name="slot", digest="d_y")]),
                _node(node_id="fallback", outputs=[IOSpec(name="slot", digest="d_fallback")]),
            ],
            edges=[
                _contains(source="outer", target="inner"),
                _contains(source="outer", target="fallback"),
                _contains(source="inner", target="x"),
                _contains(source="inner", target="y"),
            ],
        )
        inner_merge = ConditionOutputMerge(condition_node_id="inner", shared_digest="d_y", merged_digests=["d_x"])
        outer_merge = ConditionOutputMerge(condition_node_id="outer", shared_digest="d_fallback", merged_digests=["d_y"])
        merges = [inner_merge, outer_merge] if inner_first else [outer_merge, inner_merge]

        merged = apply_condition_output_merges(graph=graph, merges=merges)

        assert {node_id: [spec.digest for spec in specs] for node_id, specs in _outputs_by_node(merged).items()} == {
            "outer": ["d_fallback"],
            "inner": ["d_fallback"],
            "x": ["d_fallback"],
            "y": ["d_fallback"],
            "fallback": ["d_fallback"],
        }

    def test_a_nested_typing_retypes_the_inner_condition_item(self) -> None:
        """A typing names the item by the digest it had when recorded, which a later merge may move."""
        graph = self._graph(
            nodes=[
                _node(node_id="outer", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Text", digest="d_fallback")]),
                _node(node_id="inner", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="slot", concept="Email", digest="d_y")]),
                _node(node_id="x", outputs=[IOSpec(name="slot", concept="Question", digest="d_x")]),
                _node(node_id="y", outputs=[IOSpec(name="slot", concept="Email", digest="d_y")]),
                _node(node_id="fallback", outputs=[IOSpec(name="slot", concept="Text", digest="d_fallback")]),
            ],
            edges=[],
        )
        merges = [
            ConditionOutputMerge(
                condition_node_id="inner",
                shared_digest="d_y",
                merged_digests=["d_x"],
                shared_typing=ConditionOutputTyping(concept="Anything", multiplicity=None),
            ),
            ConditionOutputMerge(condition_node_id="outer", shared_digest="d_fallback", merged_digests=["d_y"]),
        ]

        merged = apply_condition_output_merges(graph=graph, merges=merges)

        inner_output = _outputs_by_node(merged)["inner"][0]
        assert inner_output.digest == "d_fallback"
        assert inner_output.concept == "Anything"
        assert _outputs_by_node(merged)["outer"][0].concept == "Text"

    def test_stuff_to_stuff_edges_follow_the_merge(self) -> None:
        graph = self._graph(
            nodes=[
                _node(node_id="route", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="answers", digest="d_default")]),
                _node(node_id="ask_each", kind=NodeKind.CONTROLLER, outputs=[IOSpec(name="answers", multiplicity=True, digest="d_batch")]),
                _node(node_id="ask_one", outputs=[IOSpec(name="answer", digest="d_item_0")]),
                _node(node_id="write_default", outputs=[IOSpec(name="answers", multiplicity=True, digest="d_default")]),
            ],
            edges=[
                EdgeSpec(
                    edge_id="aggregate",
                    source="ask_one",
                    target="ask_each",
                    kind=EdgeKind.BATCH_AGGREGATE,
                    source_stuff_digest="d_item_0",
                    target_stuff_digest="d_batch",
                ),
                EdgeSpec(
                    edge_id="combine",
                    source="ask_one",
                    target="ask_each",
                    kind=EdgeKind.PARALLEL_COMBINE,
                    source_stuff_digest="d_batch",
                    target_stuff_digest="d_other",
                ),
                _contains(source="route", target="ask_each"),
            ],
        )
        merge = ConditionOutputMerge(condition_node_id="route", shared_digest="d_default", merged_digests=["d_batch"])

        merged = apply_condition_output_merges(graph=graph, merges=[merge])

        edges = {edge.edge_id: edge for edge in merged.edges}
        assert (edges["aggregate"].source_stuff_digest, edges["aggregate"].target_stuff_digest) == ("d_item_0", "d_default")
        assert (edges["combine"].source_stuff_digest, edges["combine"].target_stuff_digest) == ("d_default", "d_other")
        assert (edges["contains_route_ask_each"].source_stuff_digest, edges["contains_route_ask_each"].target_stuff_digest) == (None, None)
        assert _outputs_by_node(merged)["ask_one"][0].digest == "d_item_0"
